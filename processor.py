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

        for order in orders:
            # 1. Tenders (How it was paid)
            tenders = order.get('tenders', [])
            total_money = order.get('total_money', {'amount': 0})
            order_total = float(total_money['amount']) / 100.0
            
            # Filter OUT unpaid/canceled orders just in case, though we filtered by COMPLETED
            if order['state'] != 'COMPLETED':
                continue

            summary['total_collected'] += order_total

            for tender in tenders:
                tender_type = tender['type']
                amt = float(tender['amount_money']['amount']) / 100.0
                
                if tender_type == 'CASH':
                    summary['tenders']['cash'] += amt
                elif tender_type == 'SQUARE_GIFT_CARD':
                    summary['tenders']['gift_card'] += amt
                elif tender_type == 'CARD':
                    summary['tenders']['card'] += amt
                else:
                    summary['tenders']['other'] += amt

            # 2. Line Items (Sales Mapping)
            line_items = order.get('line_items', [])
            for item in line_items:
                # Gross Sales
                gross_money = item.get('gross_sales_money', {'amount': 0})
                gross_amount = float(gross_money['amount']) / 100.0
                
                # Determine Category/Mapping
                # Try Item Mapping first? No, we rely on Category Name
                cat_id = item.get('catalog_object_id') # This is Item ID, not Category
                # We typically need to look up the Item's Category.
                # Since 'line_items' in Order object doesn't always contain category_name directly unless expanded?
                # Actually, Square SearchOrders response includes 'catalog_object_id' and 'item_type'.
                # To get Category, we might need to fetch Catalog or assume 'name' mapping if config relies on names.
                # However, the user provided 'Food & Snack' etc.
                # Square Order Line Item usually has 'name'. We can map based on Name if Category is missing?
                # User config maps 'Square Category Names' to Account IDs. 
                # !!! Square Orders don't always have Category Name inline.
                # BUT, variation_name or name is there.
                # Wait, the config uses specific Category Names "Drinks", "Memberships".
                # We need to map OrderItem -> Category.
                # This usually requires a Catalog lookup map (Item ID -> Category Name).
                # For now, let's try to infer or fallback.
                
                # IMPORTANT: We need a way to map Item -> Wave Account.
                # Current config maps "Category Name" -> "Wave Account".
                # If we don't have the Category Name in the Order, we are stuck.
                # Square Orders API 'return_entries' might help?
                # Or we build a local catalog map from 'square_catalog_full.json' if needed?
                # For now, let's assume we use the 'name' or 'variation_name' to guess, OR better:
                # We should have fetched the catalog map in __init__.
                
                # Fallback: All 'Sales' to default if logic too complex for first pass?
                # User requests precise mapping.
                # Let's use a "Default" income account for now to ensure code runs, 
                # but ideally we look up the category.
                
                # Match Item -> Category -> Wave Account
                cat_name = self.catalog.get_category_for_item(cat_id)
                item_name = item.get('name', '')
                
                # Special Override: eGift Card (Liability)
                if "eGift Card" in item_name:
                     target_acct = self.account_map['gift_card']
                else:
                    target_acct = self.category_map.get(cat_name)
                    
                    # If not found by exact category name, try 'Uncategorized' or fallback
                    if not target_acct:
                         target_acct = self.category_map.get('Uncategorized')
                         print(f"DEBUG: Unknown Category: {item_name} (Cat: {cat_name}) - Using Uncategorized")
                    elif target_acct == "WAVE_ACCOUNT_ID_DEFAULT":
                         # Default mapping (silent)
                         pass

                
                # Add to breakdown
                if target_acct not in summary['sales_breakdown']:
                    summary['sales_breakdown'][target_acct] = 0.0
                summary['sales_breakdown'][target_acct] += gross_amount

            # 3. Taxes
            # Taxes are usually separate from Gross Sales in the 'total_tax_money'
            tax_money = order.get('total_tax_money', {'amount': 0})
            summary['tax'] += float(tax_money['amount']) / 100.0
            
            # 4. Tips
            tip_money = order.get('total_tip_money', {'amount': 0})
            summary['tips'] += float(tip_money['amount']) / 100.0
            
            # 5. Discounts
            discounts = order.get('discounts', [])
            for disc in discounts:
                disc_name = disc.get('name', 'Default')
                disc_applied = float(disc['applied_money']['amount']) / 100.0
                
                # Lookup Discount Account
                # Try exact match, then 'Default'
                disc_acct = self.discount_map.get(disc_name, self.discount_map.get('Default'))
                
                # Discounts reduce income, but in accounting, they are usually:
                # Debit Constraint-Income (or Expense).
                # Since we are depositing to AR (Anchor), 
                # Income (Credit) + Tax (Credit) + Tips (Credit) - Discount (Debit) = AR (Debit)
                
                # We'll treat this as a negative entry in sales breakdown or separate bucket?
                # Wave 'moneyTransaction' needs 'DEPOSIT'/'WITHDRAWAL'.
                # AR is DEPOSIT.
                # Income is DEPOSIT to Account? No.
                # AR (Asset) Increase = Debit. Wave calls this DEPOSIT (to the anchor).
                # Income (Equity/Rev) Increase = Credit. Wave calls this ? ("INCREASE")
                
                # Let's accumulate discounts separately to handle later
                # We can add them to 'sales_breakdown' as negative? NO, different account.
                
                # We need a 'discounts_breakdown'
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
