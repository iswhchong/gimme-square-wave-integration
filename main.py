from square_client import SquareClient
from wave_client import WaveClient
from processor import Processor
import argparse
import logging
import config
from idempotency import deterministic_external_id, content_hash, PostedLedger

logger = logging.getLogger("square_to_wave")


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
        ledger.record(
            external_id=external_id,
            hash_value=new_hash,
            amount=payload["amount"],
            wave_transaction_id=tx_id,
            extra={"role": role, "date": payload["date"], "description": payload["description"]},
        )
        logger.info("POSTED %s -> Wave tx %s", external_id, tx_id)
        return "posted"

    logger.error("FAILED to post %s (Wave returned no transaction id)", external_id)
    return "failed"

def main():
    parser = argparse.ArgumentParser(description="Square to Wave Integration")
    parser.add_argument("--date", help="Date to process (YYYY-MM-DD)", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Calculate but do not post to Wave")
    parser.add_argument("--type", help="Filter transaction type (sales_journal, transfer)", default=None)
    parser.add_argument("--replace", action="store_true",
                        help="If a day was already posted but its amounts have since changed, supersede the previous post instead of refusing.")
    parser.add_argument("--ledger", default="logs/posted_ledger.jsonl",
                        help="Path to the append-only posted-transactions ledger.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    date_str = args.date
    
    # 1. Fetch
    sq = SquareClient()
    orders = sq.fetch_orders(date_str, date_str)
    
    if not orders:
        print(f"No orders found for {date_str}.")
        return

    # 2. Process
    proc = Processor()
    summary = proc.aggregate_daily_orders(orders, date_str)
    
    print("\n--- Daily Summary ---")
    print(f"Total Collected: ${summary['total_collected']:.2f}")
    print(f"Tax: ${summary['tax']:.2f}")
    print(f"Tips: ${summary['tips']:.2f}")
    print("Sales Breakdown:")
    for acct, amt in summary['sales_breakdown'].items():
        print(f"  - Account {acct}: ${amt:.2f}")
    print("Tenders:")
    for curr, amt in summary['tenders'].items():
        print(f"  - {curr}: ${amt:.2f}")

    # 3. Post
    payloads = proc.prepare_wave_transactions(summary)
    
    if args.dry_run:
        print("\n[DRY RUN] Would create the following Wave transactions:")
        for p in payloads:
            print(f"Type: {p['type']}, Desc: {p['description']}, Amount: {p['amount']}")
            if 'anchor_id' in p:
                 print(f"   Anchor: {p['anchor_id']} ({p['anchor_direction']})")
            for l in p['lines']:
                print(f"   -> Line: {l['direction']} ${l['amount']} (Acct: {l['account_id']})")
    else:
        wv = WaveClient()
        ledger = PostedLedger(args.ledger)
        print("\n--- Posting to Wave ---")
        outcomes = {}
        for p in payloads:
            if args.type and p['type'] != args.type:
                continue

            result = _post_payload_idempotent(wv, p, ledger, replace=args.replace)
            outcomes[result] = outcomes.get(result, 0) + 1

        logger.info("Run complete for %s: %s", date_str,
                    ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items())) or "nothing to post")
        if outcomes.get("skipped_changed"):
            logger.warning("Some payloads changed since a prior post and were NOT updated. "
                           "Review, then re-run with --replace if the new figures are correct.")

if __name__ == "__main__":
    main()
