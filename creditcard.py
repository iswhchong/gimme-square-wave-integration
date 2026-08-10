r"""
CIBC Credit-card spending -> Wave entrypoint (Workstream 3).

Reads a downloaded CIBC statement CSV and posts each charge/refund/payment to Wave
against the CIBC Credit Card liability, categorized from your history (unmapped
charges -> Uncategorized Expense; card payments -> Uncategorized Income placeholder
you re-point to "Transfer from Cash on Hand").

Reuses the Phase 1 stack: deterministic per-row external id (CC_<hash>) + ledger
for idempotency, the prepare->approve->post gate, logging, and exit codes.

Usage:
  python creditcard.py --file statements\cibc_feb.csv --dry-run
  python creditcard.py --file statements\cibc_feb.csv --prepare
  python creditcard.py --approve --approval-file logs\approval_cc_<name>.json
  python creditcard.py --post    --approval-file logs\approval_cc_<name>.json
  python creditcard.py --file statements\cibc_feb.csv --force-oneshot

This is run per statement (e.g. monthly), NOT part of the daily job.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

import approval
import config
from cibc_statement import parse_statement
from cc_processor import CreditCardProcessor
from errors import PipelineError, ValidationError
from idempotency import PostedLedger
from logging_setup import setup_logging, get_logger
from validation import validate_payloads
from wave_client import WaveClient
from main import _post_payloads, post_approved, _post_status, EXIT_OK, EXIT_FAILURE, EXIT_USAGE

logger = get_logger()


def _check_accounts_configured(payloads):
    """Refuse to proceed if any payload references an unconfigured (TODO) account."""
    bad = set()
    for p in payloads:
        ids = [p.get("anchor_id")] + [l.get("account_id") for l in p.get("lines", [])]
        for i in ids:
            if isinstance(i, str) and i.startswith("TODO_"):
                bad.add(i)
    if bad:
        raise ValidationError(
            "Wave account id(s) not configured yet: " + ", ".join(sorted(bad)) +
            ". Create the account(s) in Wave and set them in config.CC_ACCOUNTS.")


def build_artifact(name, payloads):
    return {
        "schema": approval.SCHEMA,
        "kind": "creditcard",
        "date": name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "payloads": payloads,
        "payloads_fingerprint": approval.payloads_fingerprint(payloads),
        "approved": False,
        "approved_at_utc": None,
        "approved_by": None,
    }


def default_artifact_path(file_path, base_dir="logs"):
    stem = os.path.splitext(os.path.basename(file_path))[0]
    return os.path.join(base_dir, f"approval_cc_{stem}.json")


def _build_from_file(file_path):
    rows = parse_statement(file_path)
    if not rows:
        logger.warning("No transactions parsed from %s.", file_path)
        return []
    proc = CreditCardProcessor()
    payloads = proc.build_payloads(rows)
    _check_accounts_configured(payloads)          # raises if TODO ids remain
    errors = validate_payloads(payloads)
    if errors:
        logger.error("%d payload validation issue(s): %s", len(errors), "; ".join(errors))
        raise ValidationError(f"{file_path}: {len(errors)} validation issue(s)")
    for line in proc.summarize(payloads):
        logger.info(line)
    return payloads


def run_dry_run(file_path):
    try:
        payloads = _build_from_file(file_path)
    except PipelineError as e:
        logger.error("Dry-run stopped: %s", e)
        return EXIT_OK
    logger.info("[DRY RUN] %d transaction(s) would be posted from %s.", len(payloads), file_path)
    return EXIT_OK


def run_prepare(file_path, approval_file):
    payloads = _build_from_file(file_path)
    if not payloads:
        return EXIT_OK
    approval.write_artifact(approval_file, build_artifact(os.path.basename(file_path), payloads))
    logger.info("Prepared credit-card approval artifact -> %s (NOT approved, NOT posted).", approval_file)
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
    _check_accounts_configured(artifact.get("payloads", []))
    wv = WaveClient()
    ledger = PostedLedger(ledger_path)
    logger.info("--- Posting approved credit-card charges %s to Wave ---", approval_file)
    outcomes = post_approved(wv, artifact, ledger, replace=replace)
    if outcomes is None:
        return EXIT_FAILURE
    return _post_status(outcomes)


def run_force_oneshot(file_path, ledger_path, replace):
    logger.warning("FORCE one-shot credit-card post for %s: bypassing the approval gate.", file_path)
    payloads = _build_from_file(file_path)
    if not payloads:
        return EXIT_OK
    wv = WaveClient()
    ledger = PostedLedger(ledger_path)
    logger.info("--- Posting credit-card charges to Wave (force one-shot) ---")
    outcomes = _post_payloads(wv, payloads, ledger, os.path.basename(file_path), replace=replace)
    return _post_status(outcomes)


def main():
    ap = argparse.ArgumentParser(description="CIBC Credit-card spending -> Wave")
    ap.add_argument("--file", help="Path to the downloaded CIBC statement CSV.")
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
    approver = args.approver or os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    approval_file = args.approval_file
    if approval_file is None and args.file:
        approval_file = default_artifact_path(args.file)

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

    logger.info("Credit-card run start: mode=%s file=%s replace=%s approval_file=%s",
                mode, args.file, args.replace, approval_file)

    if mode in ("prepare", "dry-run", "force-oneshot") and not args.file:
        logger.error("--file is required for mode '%s'.", mode)
        return EXIT_USAGE
    if mode in ("approve", "post") and not approval_file:
        logger.error("--approval-file is required for mode '%s'.", mode)
        return EXIT_USAGE

    try:
        if mode == "dry-run":
            code = run_dry_run(args.file)
        elif mode == "prepare":
            code = run_prepare(args.file, approval_file)
        elif mode == "approve":
            code = run_approve(approval_file, approver)
        elif mode == "post":
            code = run_post(approval_file, args.ledger, args.replace)
        elif mode == "force-oneshot":
            code = run_force_oneshot(args.file, args.ledger, args.replace)
        else:
            code = EXIT_OK
    except PipelineError as e:
        logger.error("Credit-card run failed: %s", e)
        code = EXIT_FAILURE
    except Exception as e:
        logger.exception("Unexpected error during credit-card %s run: %s", mode, e)
        code = EXIT_FAILURE

    logger.info("Run log written to %s (exit=%d)", log_path, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
