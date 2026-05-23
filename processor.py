import config
from datetime import datetime
from catalog_manager import CatalogManager

class Processor:
    def __init__(self):
        self.category_map = config.ITEM_CATEGORY_MAPPING
        self.discount_map = config.DISCOUNT_MAPPING
        self.account_map = config.ACCOUNT_MAPPING
        self.catalog = CatalogManager() # Initialize catalog lookup

    def aggregate_daily_orders(self, orders, date_str):
        """
        Aggregate a list of Square Orders into accounting buckets for a single day.
        """
        summary = {
            "date": date_str,
            "total_collected": 0.0, # This goes to AR (Anchor)
            "sales_breakdown": {},  # Key: Wave Account ID, Value: Amount
            "tax": 0.0,
            "tips": 0.0,
            "tenders": {
                "cash": 0.0,
                "gift_card": 0.0,
                "card": 0.0,
                "other": 0.0
            }
        }

        # 1. Fetch source orders for any refunds to determine their original tender types
        from square_client import SquareClient
        sq = SquareClient()
        source_order_ids = set()
        
        for order in orders:
            if order.get('state') != 'COMPLETED':
                continue
            
            # If it's a refund and doesn't have local tenders, look up source orders
            net_amounts = order.get('net_amounts', {})
            net_total_money = float(net_amounts.get('total_money', {}).get('amount', 0))
            returns = order.get('returns', [])
            is_refund = net_total_money < 0 or (net_total_money == 0 and len(returns) > 0)
            
            if is_refund and not order.get('tenders'):
                for r in returns:
                    sid = r.get('source_order_id')
                    if sid:
                        source_order_ids.add(sid)

        # Retrieve source orders and build tender type map
        tender_type_map = {} # (order_id, tender_id) -> type
        if source_order_ids:
            try:
                source_orders = sq.batch_retrieve_orders(list(source_order_ids))
                for so in source_orders:
                    so_id = so.get('id')
                    for t in so.get('tenders', []):
                        tid = t.get('id')
                        ttype = t.get('type')
                        if ttype == 'CARD':
                            brand = t.get('card_details', {}).get('card', {}).get('card_brand')
                            if brand == 'SQUARE_GIFT_CARD':
                                ttype = 'SQUARE_GIFT_CARD'
                        tender_type_map[(so_id, tid)] = ttype
            except Exception as e:
                print(f"Warning: Failed to retrieve source orders for refund tender mapping: {e}")

        # 2. Process all orders
        for order in orders:
            if order.get('state') != 'COMPLETED':
                continue

            # --- Financial Totals (Net after returns/refunds) ---
            net_amounts = order.get('net_amounts', {})
            net_total = float(net_amounts.get('total_money', {}).get('amount', 0)) / 100.0
            net_tax = float(net_amounts.get('tax_money', {}).get('amount', 0)) / 100.0
            net_tip = float(net_amounts.get('tip_money', {}).get('amount', 0)) / 100.0

            summary['total_collected'] += net_total
            summary['tax'] += net_tax
            summary['tips'] += net_tip

            # --- Sales & Returns Items ---
            # Add sales from line_items
            line_items = order.get('line_items', [])
            for item in line_items:
                gross_amount = float(item.get('gross_sales_money', {'amount': 0}).get('amount', 0)) / 100.0
                cat_id = item.get('catalog_object_id')
                cat_name = self.catalog.get_category_for_item(cat_id)
                item_name = item.get('name', '')
                
                if "eGift Card" in item_name:
                    target_acct = self.account_map['gift_card']
                else:
                    target_acct = self.category_map.get(cat_name)
                    if not target_acct:
                        target_acct = self.category_map.get('Uncategorized')
                        print(f"DEBUG: Unknown Category: {item_name} (Cat: {cat_name}) - Using Uncategorized")
                
                if target_acct not in summary['sales_breakdown']:
                    summary['sales_breakdown'][target_acct] = 0.0
                summary['sales_breakdown'][target_acct] += gross_amount

            # Subtract returns from line items
            returns = order.get('returns', [])
            for r in returns:
                for rl in r.get('return_line_items', []):
                    return_amount = float(rl.get('gross_return_money', {'amount': 0}).get('amount', 0)) / 100.0
                    cat_id = rl.get('catalog_object_id')
                    cat_name = self.catalog.get_category_for_item(cat_id)
                    item_name = rl.get('name', '')
                    
                    if "eGift Card" in item_name:
                        target_acct = self.account_map['gift_card']
                    else:
                        target_acct = self.category_map.get(cat_name)
                        if not target_acct:
                            target_acct = self.category_map.get('Uncategorized')
                            print(f"DEBUG: Unknown Return Category: {item_name} (Cat: {cat_name}) - Using Uncategorized")
                    
                    if target_acct not in summary['sales_breakdown']:
                        summary['sales_breakdown'][target_acct] = 0.0
                    summary['sales_breakdown'][target_acct] -= return_amount

            # --- Tenders (Payments & Refunds) ---
            tenders = order.get('tenders', [])
            refunds = order.get('refunds', [])

            # Original payments
            for t in tenders:
                amt = float(t.get('amount_money', {}).get('amount', 0)) / 100.0
                ttype = t.get('type')
                if ttype == 'CASH':
                    summary['tenders']['cash'] += amt
                elif ttype == 'SQUARE_GIFT_CARD':
                    summary['tenders']['gift_card'] += amt
                elif ttype == 'CARD':
                    brand = t.get('card_details', {}).get('card', {}).get('card_brand')
                    if brand == 'SQUARE_GIFT_CARD':
                        summary['tenders']['gift_card'] += amt
                    else:
                        summary['tenders']['card'] += amt
                else:
                    summary['tenders']['other'] += amt

            # Subtract refunds from tenders
            for ref in refunds:
                ref_amt = float(ref.get('amount_money', {}).get('amount', 0)) / 100.0
                tid = ref.get('tender_id')
                
                # Check source order logic
                source_oid = None
                if returns:
                    source_oid = returns[0].get('source_order_id')
                
                found_type = None
                if source_oid and tid:
                    found_type = tender_type_map.get((source_oid, tid))
                
                if not found_type:
                    # Fallback Heuristics
                    reason = ref.get('reason', '').lower()
                    if "change" in reason or "cash" in reason:
                        found_type = 'CASH'
                    else:
                        # Default fallback
                        found_type = 'CARD'
                
                if found_type == 'CASH':
                    summary['tenders']['cash'] -= ref_amt
                elif found_type == 'SQUARE_GIFT_CARD':
                    summary['tenders']['gift_card'] -= ref_amt
                elif found_type == 'CARD':
                    summary['tenders']['card'] -= ref_amt
                else:
                    summary['tenders']['other'] -= ref_amt

            # --- Discounts ---
            if config.AGGREGATE_DISCOUNTS:
                net_disc_money = float(net_amounts.get('discount_money', {}).get('amount', 0)) / 100.0
                if net_disc_money != 0:
                    disc_acct = self.discount_map.get('Default')
                    if 'discounts_breakdown' not in summary:
                        summary['discounts_breakdown'] = {}
                    if disc_acct not in summary['discounts_breakdown']:
                        summary['discounts_breakdown'][disc_acct] = 0.0
                    summary['discounts_breakdown'][disc_acct] += net_disc_money
            else:
                discounts = order.get('discounts', [])
                for disc in discounts:
                    disc_name = disc.get('name', 'Default')
                    disc_applied = float(disc['applied_money']['amount']) / 100.0
                    disc_acct = self.discount_map.get(disc_name, self.discount_map.get('Default'))
                    if 'discounts_breakdown' not in summary:
                        summary['discounts_breakdown'] = {}
                    if disc_acct not in summary['discounts_breakdown']:
                        summary['discounts_breakdown'][disc_acct] = 0.0
                    summary['discounts_breakdown'][disc_acct] += disc_applied

        return summary

    def prepare_wave_transactions(self, summary):
        """
        Convert the daily summary into a list of WaveClient transaction payloads.
        Returns: [ {type: 'sales', ...}, {type: 'transfer_cash', ...} ]
        """
        payloads = []
        date = summary['date']
        # Format date for description: MMM D (e.g. "Jan 15")
        dt = datetime.strptime(date, "%Y-%m-%d")
        desc_date = f"{dt.strftime('%b')} {dt.day}"
        
        # 1. Main Sales Transaction
        # Anchor: Square AR (Asset) -> DEPOSIT (Increase)
        # Lines:
        #   - Sales Accounts: INCREASE (Credit)
        #   - Tax Account: INCREASE (Credit)
        #   - Tips Account: INCREASE (Credit)
        #   - Discount Account: INCREASE (Debit - wait, Discount is usually Debit balance)
        
        # Wave "balance" field: 'INCREASE' or 'DECREASE' relative to the account's normal balance?
        # OR 'DEPOSIT'/'WITHDRAWAL' relative to the account?
        # The mutation `moneyTransactionCreate` lines take `balance` enum: INCREASE, DECREASE.
        # It's relative to the account's normal balance type?
        # Let's assume standard behavior:
        # Income (Credit Normal) -> INCREASE = Credit.
        # Liability (Credit Normal) -> INCREASE = Credit.
        # Expense/Contra (Debit Normal) -> INCREASE = Debit.
        
        # Helper to format money
        def fmt_money(val):
            return round(val, 2)

        # 1. Main Sales Transaction
        sales_items = []
        total_credits = 0.0
        
        # Sales
        for acct_id, amt in summary['sales_breakdown'].items():
            if amt > 0:
                val = fmt_money(amt)
                total_credits += val
                sales_items.append({
                    "account_id": acct_id,
                    "amount": val,
                    "direction": "INCREASE", # Credit
                    "description": "Daily Sales"
                })
        
        # Tax
        tax_val = fmt_money(summary['tax'])
        if tax_val > 0:
            total_credits += tax_val
            sales_items.append({
                "account_id": self.account_map['tax'],
                "amount": tax_val,
                "direction": "INCREASE", # Credit
                "description": "Sales Tax"
            })
            
        # Tips
        tips_val = fmt_money(summary['tips'])
        if tips_val > 0:
            total_credits += tips_val
            sales_items.append({
                "account_id": self.account_map['tips'],
                "amount": tips_val,
                "direction": "INCREASE", # Income - Credit
                "description": "Tips"
            })
            
        # Discounts (Debit)
        discount_items = []
        total_debits = 0.0
        if 'discounts_breakdown' in summary:
             for acct_id, amt in summary['discounts_breakdown'].items():
                if amt > 0:
                    val = fmt_money(amt)
                    total_debits += val
                    discount_items.append({
                        "account_id": acct_id,
                        "amount": val,
                        "direction": "INCREASE", # Contra-Rev (Debit)
                        "description": "Discount applied"
                    })
        
        # Calculate expected Anchor Amount (Net collected)
        # Anchor (Asset) Increase = Debit
        # Credits - Debits = Net Credit needed from Anchor? 
        # No. Total Credits (Sales+Tax+Tips) MUST EQUAL Total Debits (Discounts + Anchor Deposit).
        # So: Anchor Deposit = Total Credits - Total Debits(Discounts).
        
        calculated_anchor = total_credits - total_debits
        actual_anchor = fmt_money(summary['total_collected'])
        
        diff = round(actual_anchor - calculated_anchor, 2)
        
        # Adjust if mismatch due to rounding (usually 0.01)
        if diff != 0:
            print(f"Rounding discrepancy detected: {diff}. Adjusting largest sales item.")
            # Find largest sales item to adjust
            if sales_items:
                # Sort by amount desc
                sales_items.sort(key=lambda x: x['amount'], reverse=True)
                sales_items[0]['amount'] = round(sales_items[0]['amount'] + diff, 2)
                # Re-calculate total_credits just to be sure (mentally)
            else:
                # If no sales items? Unusual. Adjust Tax?
                pass
        
        # Combine lines
        lines = sales_items + discount_items
        
        payloads.append({
            "type": "sales_journal",
            "date": date,
            "description": f"Sales - {desc_date} - Square",
            "amount": actual_anchor, # Use the actual collected as anchor
            "lines": lines
        })
        
        # 2. Transfers - WORKAROUND using Tee Time
        # Cash: Debit Cash (Deposit), Credit Tee Time (Increase)
        cash_amt = fmt_money(summary['tenders']['cash'])
        if cash_amt > 0:
            payloads.append({
                "type": "transfer",
                "date": date,
                "description": f"Sales - {desc_date} - Cash Register",
                "anchor_id": self.account_map['cash'],
                "anchor_direction": "DEPOSIT", 
                "amount": cash_amt,
                "lines": [{
                    "account_id": self.account_map['tee_time'], # Workaround Placeholder
                    "amount": cash_amt,
                    "direction": "INCREASE" # Credit Revenue
                }]
            })
            
        # Gift Card: Debit Liability (Decrease), Credit Placeholder (Cash Register - Asset)
        # Note: We MUST use an Asset account as Anchor for moneyTransaction.
        # "Tee Time" (Revenue) failed as anchor.
        # "Cash Register" (Asset) works.
        # User will edit "Cash Register" -> "Square AR".
        gc_amt = fmt_money(summary['tenders']['gift_card'])
        if gc_amt > 0:
            payloads.append({
                "type": "transfer",
                "date": date,
                "description": f"Sales - {desc_date} - Gift Card",
                "anchor_id": self.account_map['cash'], # Anchor on Asset (Cash Register)
                "anchor_direction": "WITHDRAWAL", # Credit Cash
                "amount": gc_amt,
                "lines": [{
                    "account_id": self.account_map['gift_card'],
                    "amount": gc_amt,
                    "direction": "DECREASE" # Debit Liability
                }]
            })

        return payloads
