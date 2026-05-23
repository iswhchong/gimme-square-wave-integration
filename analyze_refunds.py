import json
import pytz
from datetime import datetime
import pandas as pd
import sys

with open("analysis_refunds.txt", "w") as out:
    sys.stdout = out
    
    with open("orders_dump_refunds.json", "r") as f:
        orders = json.load(f)

    print(f"Loaded {len(orders)} orders.")
    
    # Targets
    targets = [
        {"amt": 12275, "time": "23:56:04", "date": "2026-01-03"},
        {"amt": 3485, "time": "12:58:06", "date": "2026-01-06"}
    ]
    
    tz_edmonton = pytz.timezone('America/Edmonton')

    for o in orders:
        # Check Net Amount or Refund Amount?
        # Net amount would be negative if full refund?
        net_total = float(o.get('net_amounts', {}).get('total_money', {}).get('amount', 0))
        
        # Check Returns
        returns = o.get('returns', [])
        total_return_amt = 0
        for r in returns:
            # return amounts are positive in API
            total_return_amt += float(r.get('return_amounts', {}).get('total_money', {}).get('amount', 0))
            
        found = False
        # Check if this order matches any target
        for t in targets:
            # Check amounts (Net or Return)
            # 122.75 -> 12275
            if abs(net_total) == t['amt'] or total_return_amt == t['amt']:
                found = True
            
            # Check Time
            created_at = o.get('created_at', '')
            if created_at:
                dt_utc = pd.to_datetime(created_at).to_pydatetime().replace(tzinfo=pytz.UTC)
                dt_local = dt_utc.astimezone(tz_edmonton)
                # Check fuzzy matches
                # print(dt_local)
        
        if found or len(returns) > 0: # Print all returns to be safe
             print(f"--- MATCH/RETURN FOUND ID: {o['id']} ---")
             print(f"Created: {o['created_at']}, Closed: {o['closed_at']}")
             print(f"Net Total: {net_total}, Return Total: {total_return_amt}")
             print(json.dumps(o, indent=2))
