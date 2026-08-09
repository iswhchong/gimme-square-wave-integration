from square_client import SquareClient
from wave_client import WaveClient
from processor import Processor
import argparse
import os
import sys
import config
from idempotency import deterministic_external_id, content_hash, PostedLedger
from logging_setup import setup_logging, get_logger
from validation import validate_summary, validate_payloads
from errors import ReconciliationError, ValidationError, PipelineError
import approval

logger = get_logger()

# Process exit codes (so an unattended/scheduled run surfaces failures):
EXIT_OK = 0        # success, or a benign no-orders day
EXIT_FAILURE = 1   # a day was aborted, refused, or failed to post
EXIT_USAGE = 2     # bad or missing arguments / inputs


def _post_payload_idempotent(wv, payload, ledger, replace=False):
    """
    Post a single prepared payload to Wave exactly once.

    Idempotency: a deterministic external id (role + location + day) plus a local
    append-only ledger of what we've already posted. On re-run:
      - already posted, content unchanged -> skip (no double-post);
      - already posted, content CHANGED   -> refuse and flag, unless replace=True;
      - not yet posted                    -> post and record.

    Returns one of: 'posted', 'skipped_duplicate', 'skipped_changed', 'failed'.
    """
    role = payload.get("role", payload.get("type"))
    external_id = deterministic_external_id(role, config.SQUARE_LOCATION_ID, payload["date"])
    new_hash = content_hash(payload)

    existing = ledger.find(external_id)
    if existing:
        if existing.get("content_hash") == new_hash:
            logger.info("SKIP already posted %s (Wave tx %s)",
                        external_id, existing.get("wave_transaction_id"))
            return "skipped_duplicate"
        if not replace:
            logger.warning(
                "CHANGED since last post %s: ledger amount %s hash %s, new amount %.2f hash %s. "
                "Refusing to double-post. Re-run with --replace to supersede.",
                external_id, existing.get("amount"), existing.get("content_hash"),
                float(payload["amount"]), new_hash,
            )
            return "skipped_changed"
        logger.warning("REPLACE posting changed content for %s (previous Wave tx %s)",
                       external_id, existing.get("wave_transaction_id"))

    tx_id = wv.create_transaction(
        date_str=payload["date"],
        description=payload["description"],
        amount=payload["amount"],
        line_items=payload["lines"],
        external_id=external_id,
        anchor_direction=payload.get("anchor_direction", "DEPOSIT"),
        anchor_account_id=payload.get("anchor_id"),
    )

    if tx_id:
        source_ids = payload.get("source_order_ids", [])
        ledger.record(
            external_id=external_id,
            hash_value=new_hash,
            amount=payload["amount"],
            wave_transaction_id=tx_id,
            extra={
                "role": role,
                "date": payload["date"],
                "description": payload["description"],
                "source_order_ids": source_ids,
            },
        )
        # Structured audit record: everything needed to trace this posting back
        # to its Square sources (Workstream 2).
        logger.info(
            "AUDIT posted date=%s role=%s external_id=%s amount=%.2f wave_tx=%s source_orders=%d",
            payload["date"], role, external_id, float(payload["amount"]), tx_id, len(source_ids),
        )
        logger.info("POSTED %s -> Wave tx %s", external_id, tx_id)
        return "posted"

    logger.error("FAILED to post %s (Wave returned no transaction id)", external_id)
    return "failed"


def _post_payloads(wv, payloads, ledger, date_str, type_filter=None, replace=False):
    """
    Post a list of payloads idempotently, all-or-nothing on hard failure.

    On a failed post we stop rather than leave the day half-posted in an unknown
    state, logging exactly what already landed so an idempotent re-run resumes
    cleanly. Returns the outcomes count dict.
    """
    outcomes = {}
    posted_ok = []
    for p in payloads:
        if type_filter and p.get("type") != type_filter:
            continue
        result = _post_payload_idempotent(wv, p, ledger, replace=replace)
        outcomes[result] = outcomes.get(result, 0) + 1
        if result in ("posted", "skipped_duplicate"):
            posted_ok.append(p.get("role", p.get("type")))
        elif result == "failed":
            logger.error(
                "Payload '%s' failed to post for %s. Stopping. "
                "Already durable this run: %s. Re-run the same date to resume.",
                p.get("role", p.get("type")), date_str, ", ".join(posted_ok) or "none",
            )
            break

    logger.info("Run complete for %s: %s", date_str,
                ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items())) or "nothing to post")
    if outcomes.get("skipped_changed"):
        logger.warning("Some payloads changed since a prior post and were NOT updated. "
                       "Review, then re-run with --replace if the new figures are correct.")
    return outcomes


def _post_status(outcomes):
    """
    Map a posting outcomes dict to an exit code. A hard failure or a
    changed-but-not-updated payload is non-zero so a scheduled run flags it;
    posted / skipped-duplicate (idempotent re-run) are success.
    """
    if not outcomes:
        return EXIT_OK
    if outcomes.get("failed") or outcomes.get("skipped_changed"):
        return EXIT_FAILURE
    return EXIT_OK


def post_approved(wv, artifact, ledger, type_filter=None, replace=False):
    """
    Post the payloads carried in an APPROVED artifact.

    The gate: refuse unless the artifact is approved and its integrity
    fingerprint still matches its payloads. Returns the outcomes dict, or None
    if the gate rejected the artifact.
    """
    ok, msg = approval.check_postable(artifact)
    if not ok:
        logger.error("Approval gate rejected posting for %s: %s", artifact.get("date"), msg)
        return None
    logger.info("Approval gate passed for %s (approved by %s at %s).",
                artifact.get("date"), artifact.get("approved_by"), artifact.get("approved_at_utc"))
    return _post_payloads(wv, artifact.get("payloads", []), ledger,
                          artifact.get("date"), type_filter=type_filter, replace=replace)


def _fetch_aggregate_prepare(date_str):
    """
    Fetch a day from Square, aggregate, log the summary, validate, and prepare
    Wave payloads.

    Returns (summary, payloads) on success, or (None, None) for a benign
    no-orders day. Raises ReconciliationError if the day won't balance, or
    ValidationError if a blocking validation issue is found — so callers can
    turn a real problem into a non-zero exit rather than a silent skip.
    """
    sq = SquareClient()
    orders = sq.fetch_orders(date_str, date_str)
    if not orders:
        logger.warning("No orders found for %s. Nothing to do.", date_str)
        return None, None

    proc = Processor()
    summary = proc.aggregate_daily_orders(orders, date_str)

    logger.info("--- Daily Summary for %s ---", date_str)
    logger.info("Total Collected: $%.2f", summary['total_collected'])
    logger.info("Tax: $%.2f  Tips: $%.2f", summary['tax'], summary['tips'])
    logger.info("Source orders aggregated: %d", len(summary.get('source_order_ids', [])))
    for acct, amt in summary['sales_breakdown'].items():
        logger.info("  Sales acct %s: $%.2f", acct, amt)
    for curr, amt in summary['tenders'].items():
        logger.info("  Tender %s: $%.2f", curr, amt)

    summary_errors, _ = validate_summary(summary)

    # prepare_wave_transactions may raise ReconciliationError; let it propagate.
    payloads = proc.prepare_wave_transactions(summary)

    payload_errors = validate_payloads(payloads)
    blocking = summary_errors + payload_errors
    if blocking:
        logger.error("%d validation issue(s) found for %s: %s",
                      len(blocking), date_str, "; ".join(blocking))
        logger.error("Refusing to proceed with %s until the above are resolved.", date_str)
        raise ValidationError(f"{date_str}: {len(blocking)} validation issue(s): "
                              + "; ".join(blocking))

    return summary, payloads


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_dry_run(date_str):
    # Dry run is an interactive preview, never a posting: surface problems in the
    # log but don't fail the process over them.
    try:
        summary, payloads = _fetch_aggregate_prepare(date_str)
    except PipelineError as e:
        logger.error("Dry-run stopped for %s: %s", date_str, e)
        return EXIT_OK
    if payloads is None:
        return EXIT_OK
    logger.info("[DRY RUN] Would create the following Wave transactions:")
    for p in payloads:
        logger.info("Type: %s, Desc: %s, Amount: %s", p['type'], p['description'], p['amount'])
        if 'anchor_id' in p:
            logger.info("   Anchor: %s (%s)", p['anchor_id'], p['anchor_direction'])
        for l in p['lines']:
            logger.info("   -> Line: %s $%s (Acct: %s)", l['direction'], l['amount'], l['account_id'])
    return EXIT_OK


def run_prepare(date_str, approval_file):
    summary, payloads = _fetch_aggregate_prepare(date_str)   # may raise -> caught in main()
    if payloads is None:
        return EXIT_OK
    artifact = approval.build_artifact(date_str, summary, payloads,
                                       location_id=config.SQUARE_LOCATION_ID)
    approval.write_artifact(approval_file, artifact)
    for line in approval.render_summary(artifact):
        logger.info(line)
    logger.info("Prepared approval artifact -> %s (NOT approved, NOT posted).", approval_file)
    logger.info("Review it, then approve with:  --approve --approval-file %s", approval_file)
    logger.info("After approval, post with:      --post --approval-file %s", approval_file)
    return EXIT_OK


def run_approve(approval_file, approver):
    if not os.path.exists(approval_file):
        logger.error("Approval file not found: %s (run --prepare first).", approval_file)
        return EXIT_USAGE
    artifact = approval.load_artifact(approval_file)
    ok, msg, artifact = approval.approve(artifact, approver)
    if not ok:
        logger.error("Cannot approve %s: %s", approval_file, msg)
        return EXIT_FAILURE
    approval.write_artifact(approval_file, artifact)
    for line in approval.render_summary(artifact):
        logger.info(line)
    logger.info("Approved %s by %s. Post with:  --post --approval-file %s",
                approval_file, artifact["approved_by"], approval_file)
    return EXIT_OK


def run_post(approval_file, ledger_path, type_filter, replace):
    if not os.path.exists(approval_file):
        logger.error("Approval file not found: %s (run --prepare and --approve first).", approval_file)
        return EXIT_USAGE
    artifact = approval.load_artifact(approval_file)
    wv = WaveClient()
    ledger = PostedLedger(ledger_path)
    logger.info("--- Posting approved artifact %s to Wave ---", approval_file)
    outcomes = post_approved(wv, artifact, ledger, type_filter=type_filter, replace=replace)
    if outcomes is None:   # gate rejected the artifact
        return EXIT_FAILURE
    return _post_status(outcomes)


def run_force_oneshot(date_str, ledger_path, type_filter, replace):
    logger.warning("FORCE one-shot post for %s: bypassing the prepare-then-approve gate. "
                   "Use --prepare/--approve/--post for the audited path.", date_str)
    summary, payloads = _fetch_aggregate_prepare(date_str)   # may raise -> caught in main()
    if payloads is None:
        return EXIT_OK
    wv = WaveClient()
    ledger = PostedLedger(ledger_path)
    logger.info("--- Posting to Wave (force one-shot) ---")
    outcomes = _post_payloads(wv, payloads, ledger, date_str, type_filter=type_filter, replace=replace)
    return _post_status(outcomes)


def main():
    parser = argparse.ArgumentParser(description="Square to Wave Integration")
    parser.add_argument("--date", help="Date to process (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calculate and log the day; post nothing, write no artifact.")
    parser.add_argument("--prepare", action="store_true",
                        help="Prepare an approval artifact for the date (default action). Posts nothing.")
    parser.add_argument("--approve", action="store_true",
                        help="Approve an existing approval artifact (--approval-file).")
    parser.add_argument("--post", action="store_true",
                        help="Post the payloads from an APPROVED approval artifact (--approval-file).")
    parser.add_argument("--force-oneshot", action="store_true",
                        help="Legacy: fetch, prepare and post in one shot, bypassing the approval gate.")
    parser.add_argument("--approval-file", default=None,
                        help="Path to the approval artifact. Defaults to logs/approval_<YYYYMMDD>.json.")
    parser.add_argument("--approver", default=None,
                        help="Name recorded as the approver (defaults to the OS user).")
    parser.add_argument("--type", help="Filter transaction type (sales_journal, transfer)", default=None)
    parser.add_argument("--replace", action="store_true",
                        help="If a day was already posted but its amounts have since changed, supersede the previous post instead of refusing.")
    parser.add_argument("--ledger", default="logs/posted_ledger.jsonl",
                        help="Path to the append-only posted-transactions ledger.")
    args = parser.parse_args()

    log_path = setup_logging()

    # Resolve the approval file path (needs a date if not given explicitly).
    approval_file = args.approval_file
    if approval_file is None and args.date:
        approval_file = approval.default_artifact_path(args.date)

    approver = args.approver or os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    # Resolve mode. Default (nothing chosen) is the SAFE one: prepare only.
    if args.approve:
        mode = "approve"
    elif args.post:
        mode = "post"
    elif args.dry_run:
        mode = "dry-run"
    elif args.force_oneshot:
        mode = "force-oneshot"
    else:
        mode = "prepare"  # includes the explicit --prepare and the no-flag default

    logger.info("Run start: mode=%s date=%s type=%s replace=%s approval_file=%s",
                mode, args.date, args.type, args.replace, approval_file)

    if mode in ("prepare", "dry-run", "force-oneshot") and not args.date:
        logger.error("--date is required for mode '%s'.", mode)
        return EXIT_USAGE
    if mode in ("approve", "post") and not approval_file:
        logger.error("--approval-file (or --date to derive it) is required for mode '%s'.", mode)
        return EXIT_USAGE

    try:
        if mode == "dry-run":
            code = run_dry_run(args.date)
        elif mode == "prepare":
            code = run_prepare(args.date, approval_file)
        elif mode == "approve":
            code = run_approve(approval_file, approver)
        elif mode == "post":
            code = run_post(approval_file, args.ledger, args.type, args.replace)
        elif mode == "force-oneshot":
            code = run_force_oneshot(args.date, args.ledger, args.type, args.replace)
        else:
            code = EXIT_OK
    except PipelineError as e:
        # Expected, typed failure (reconciliation/validation/etc.).
        logger.error("Run failed for %s: %s", args.date, e)
        code = EXIT_FAILURE
    except Exception as e:
        # Anything unexpected (network, auth, bad response) must still fail loudly.
        logger.exception("Unexpected error during %s run for %s: %s", mode, args.date, e)
        code = EXIT_FAILURE

    logger.info("Run log written to %s (exit=%d)", log_path, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
