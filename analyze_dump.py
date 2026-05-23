import json
import pytz
from datetime import datetime
import pandas as pd
import sys

with open("analysis_output.txt", "w") as out:
    sys.stdout = out
    
    with open("orders_dump_2026_01_02_03.json", "r") as f:
        orders = json.load(f)

    print(f"Loaded {len(orders)} orders.")

    # 1. Find Refund Candidate
    # User said 2026-01-02 at 22:35:55 (Edmonton time)
    tz_edmonton = pytz.timezone('America/Edmonton')

    found_refund = False
    for o in orders:
        created_at = o.get('created_at')
        if created_at:
            dt_utc = pd.to_datetime(created_at).to_pydatetime().replace(tzinfo=pytz.UTC)
            dt_local = dt_utc.astimezone(tz_edmonton)
            
            # Check if close to 22:35:55
            if dt_local.strftime("%H:%M:%S") == "22:35:55":
                print("\n--- POSSIBLE REFUND TRANSACTION ---")
                print(json.dumps(o, indent=2))
                found_refund = True
    
    if not found_refund:
        print("\nNo transaction found specifically at 22:35:55.")
        # Fallback: check for any refund
        for o in orders:
             if len(o.get('refunds', [])) > 0 or len(o.get('returns', [])) > 0:
                 print("\n--- SAMPLE REFUND/RETURN FOUND (Fallback) ---")
                 print(json.dumps(o, indent=2))
                 break

    # 2. Find Cash/Gift Card Tenders for Problem 1
    print("\n--- TENDER EXAMPLES ---")
    cash_found = False
    for o in orders:
        tenders = o.get('tenders', [])
        for t in tenders:
            t_type = t.get('type')
            if t_type == 'CASH':
                print("CASH TENDER FOUND:")
                print(json.dumps(t, indent=2))
                cash_found = True
                break 
        if cash_found:
            break

    gc_found = False
    for o in orders:
        tenders = o.get('tenders', [])
        for t in tenders:
            t_type = t.get('type') 
            if t_type == 'SQUARE_GIFT_CARD' or (t_type == 'CARD' and t.get('card_details', {}).get('card', {}).get('card_brand') == 'SQUARE_GIFT_CARD'):
                 print("GIFT CARD TENDER FOUND:")
                 print(json.dumps(t, indent=2))
                 gc_found = True
                 break
        if gc_found:
            break
