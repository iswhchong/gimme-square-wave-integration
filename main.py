from square_client import SquareClient
from wave_client import WaveClient
from processor import Processor
import argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Square to Wave Integration")
    parser.add_argument("--date", help="Date to process (YYYY-MM-DD)", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Calculate but do not post to Wave")
    parser.add_argument("--type", help="Filter transaction type (sales_journal, transfer)", default=None)
    args = parser.parse_args()

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
        print("\n--- Posting to Wave ---")
        for p in payloads:
            if args.type and p['type'] != args.type:
                continue
                
            if p['type'] == 'sales_journal':
                # Sales Journal
                wv.create_transaction(
                    date_str=p['date'],
                    description=p['description'],
                    amount=p['amount'],
                    line_items=p['lines'],
                    anchor_account_id=p.get('anchor_id')
                )
            elif p['type'] == 'transfer':
                # Transfers
                wv.create_transaction(
                     date_str=p['date'],
                     description=p['description'],
                     amount=p['amount'],
                     line_items=p['lines'],
                     anchor_direction=p.get('anchor_direction', 'DEPOSIT'),
                     anchor_account_id=p.get('anchor_id')
                ) 

if __name__ == "__main__":
    main()
