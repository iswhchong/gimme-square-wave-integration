"""
Square Payouts -> Wave entrypoint (Workstream 2), posting via the API.

Each payout posts one Wave money transaction: bank gets the net, Square's fees go
to their expense accounts, the gift-card-fee GST goes to the ITC account, and the
"transfer from Square - A/R" amount is parked in a SUSPENSE account (config
PAYOUT_ACCOUNTS['suspense']). After posting, Kent re-points that single suspense
line to "Transfer from Square - Account Receivable" in Wave and fixes the actual
settlement date. Everything else is final.

Reuses the Phase 1 stack: per-payout external id (SQ_PAYOUT_<id>) + ledger for
idempotency, the prepare->approve->post gate, logging, and exit codes.

Modes: --dry-run / --prepare (default) / --approve / --post / --force-oneshot.
Range: --date YYYY-MM-DD (single day) or --start/--end.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

import approval
import config
from errors import PipelineError, ValidationError
from idempotency import PostedLedger
from logging_setup import setup_logging, get_logger
from payout_client import PayoutClient
from payout_processor import PayoutProcessor
from validation import validate_payloads
from wave_client import WaveClient
from main import _post_payloads, post_approved, _post_status, EXIT_OK, EXIT_FAILURE, EXIT_USAGE

logger = get_logger()


def build_artifact(start, end, payloads):
    return {
        "schema": approval.SCHEMA,
        "kind": "payouts",
        "date": f"{start}..{end}",
        "range": {"start": start, "end": end},
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "payloads": payloads,
        "payloads_fingerprint": approval.payloads_fingerprint(payloads),
        "approved": False,
        "approved_at_utc": None,
        "approved_by": None,
    }


def default_artifact_path(start, end, base_dir="logs"):
    tag = start.replace("-", "") if start == end else f"{start.replace('-', '')}_{end.replace('-', '')}"
    return os.path.join(base_dir, f"approval_payouts_{tag}.json")


def render_summary(payloads):
    lines = ["--- Payout summary (transfer line posts to SUSPENSE; re-point in Wave) ---"]
    if not payloads:
        lines.append("  (no payouts to post)")
        return lines
    for p in payloads:
        r = p.get("reconciliation", {})
        lines.append(f"  {p['description']}  (payout {r.get('payout_id')})")
        lines.append(f"    net ${r.get('net'):.2f} -> bank | cc_fee ${r.get('cc_fee'):.2f} | "
                     f"gift_card_fee ${r.get('gift_card_fee_net'):.2f} + GST ${r.get('gift_card_fee_gst'):.2f} | "
                     f"suspense/transfer ${r.get('suspense_transfer'):.2f}")
    return lines


def _fetch_and_build(start, end):
    client = PayoutClient()
    records = client.fetch_payouts_with_entries(start, end)
    if not records:
        logger.warning("No payouts found for %s..%s. Nothing to do.", start, end)
        return []
    payloads = PayoutProcessor().build_payloads(records)   # may raise ReconciliationError
    if not payloads:
        logger.warning("No postable payouts for %s..%s (all skipped).", start, end)
        return []
    errors = validate_payloads(payloads)
    if errors:
        logger.error("%d payout payload validation issue(s): %s", len(errors), "; ".join(errors))
        raise ValidationError(f"{start}..{end}: {len(errors)} payout validation issue(s)")
    for line in render_summary(payloads):
        logger.info(line)
    return payloads


def run_dry_run(start, end):
    try:
        payloads = _fetch_and_build(start, end)
    except PipelineError as e:
        logger.error("Dry-run stopped: %s", e)
        return EXIT_OK
    logger.info("[DRY RUN] %d payout transaction(s) would be posted.", len(payloads))
    for p in payloads:
        for l in p["lines"]:
            logger.info("   -> %s $%.2f (acct %s)", l["direction"], l["amount"], l["account_id"])
    return EXIT_OK


def run_prepare(start, end, approval_file):
    payloads = _fetch_and_build(start, end)
    if not payloads:
        return EXIT_OK
    approval.write_artifact(approval_file, build_artifact(start, end, payloads))
    logger.info("Prepared payout approval artifact -> %s (NOT approved, NOT posted).", approval_file)
    logger.info("Approve with:  --approve --approval-file %s", approval_file)
    logger.info("Then post with: --post --approval-file %s", approval_file)
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
    logger.info("Approved %s by %s. Post with:  --post --approval-file %s",
                approval_file, artifact["approved_by"], approval_file)
    return EXIT_OK


def run_post(approval_file, ledger_path, replace):
    if not os.path.exists(approval_file):
        logger.error("Approval file not found: %s (run --prepare and --approve first).", approval_file)
        return EXIT_USAGE
    artifact = approval.load_artifact(approval_file)
    wv = WaveClient()
    ledger = PostedLedger(ledger_path)
    logger.info("--- Posting approved payouts %s to Wave ---", approval_file)
    outcomes = post_approved(wv, artifact, ledger, replace=replace)
    if outcomes is None:
        return EXIT_FAILURE
    return _post_status(outcomes)


def run_force_oneshot(start, end, ledger_path, replace):
    logger.warning("FORCE one-shot payout post for %s..%s: bypassing the approval gate.", start, end)
    payloads = _fetch_and_build(start, end)
    if not payloads:
        return EXIT_OK
    wv = WaveClient()
    ledger = PostedLedger(ledger_path)
    logger.info("--- Posting payouts to Wave (force one-shot) ---")
    outcomes = _post_payloads(wv, payloads, ledger, f"{start}..{end}", replace=replace)
    return _post_status(outcomes)


def main():
    ap = argparse.ArgumentParser(description="Square Payouts -> Wave")
    ap.add_argument("--date", help="Single day YYYY-MM-DD (sets start=end).")
    ap.add_argument("--start", help="Range start YYYY-MM-DD.")
    ap.add_argument("--end", help="Range end YYYY-MM-DD.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--force-oneshot", action="store_true")
    ap.add_argument("--approval-file", default=None)
    ap.add_argument("--approver", default=None)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--ledger", default="logs/posted_ledger.jsonl")
    args = ap.parse_args()

    log_path = setup_logging()
    start = args.start or args.date
    end = args.end or args.date
    approver = args.approver or os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    approval_file = args.approval_file
    if approval_file is None and start and end:
        approval_file = default_artifact_path(start, end)

    if args.approve:
        mode = "approve"
    elif args.post:
        mode = "post"
    elif args.dry_run:
        mode = "dry-run"
    elif args.force_oneshot:
        mode = "force-oneshot"
    else:
        mode = "prepare"

    logger.info("Payouts run start: mode=%s range=%s..%s replace=%s approval_file=%s",
                mode, start, end, args.replace, approval_file)

    if mode in ("prepare", "dry-run", "force-oneshot") and not (start and end):
        logger.error("--date (or --start/--end) is required for mode '%s'.", mode)
        return EXIT_USAGE
    if mode in ("approve", "post") and not approval_file:
        logger.error("--approval-file (or --date to derive it) is required for mode '%s'.", mode)
        return EXIT_USAGE

    try:
        if mode == "dry-run":
            code = run_dry_run(start, end)
        elif mode == "prepare":
            code = run_prepare(start, end, approval_file)
        elif mode == "approve":
            code = run_approve(approval_file, approver)
        elif mode == "post":
            code = run_post(approval_file, args.ledger, args.replace)
        elif mode == "force-oneshot":
            code = run_force_oneshot(start, end, args.ledger, args.replace)
        else:
            code = EXIT_OK
    except PipelineError as e:
        logger.error("Payouts run failed for %s..%s: %s", start, end, e)
        code = EXIT_FAILURE
    except Exception as e:
        logger.exception("Unexpected error during payouts %s run for %s..%s: %s", mode, start, end, e)
        code = EXIT_FAILURE

    logger.info("Run log written to %s (exit=%d)", log_path, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
