import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
import argparse
import config
from square_client import SquareClient
from catalog_manager import CatalogManager
import pytz

# Constants
SHEET_ID = "1iQAF7kblDt9TdQMG1vPC5kfDnvCIdfiacRdnSSX4qWI"
KEY_FILE = "service_account.json"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

class SquareToSheets:
    def __init__(self):
        self.sq = SquareClient() # No args, reads from config
        self.catalog = CatalogManager() # No args, reads local json
        self.client = self._auth_google()
        self.sh = self.client.open_by_key(SHEET_ID)

    def _auth_google(self):
        creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_FILE, SCOPE)
        return gspread.authorize(creds)

    def process_orders(self, orders, tx_headers, item_headers):
        tx_rows = []
        item_rows = []

        # Prepare Source Order Lookup for Refunds without Tenders
        refund_map = {} # order_id -> {tender_id -> type}
        source_order_ids = set()
        
        # First pass: Identify refunds needing lookup
        for order in orders:
                net_total = float(order.get('net_amounts', {}).get('total_money', {}).get('amount', 0))
                returns = order.get('returns', [])
                is_refund = net_total < 0 or (net_total == 0 and len(returns) > 0)
                
                # Check if tenders are empty. Most pure refunds have empty tenders list.
                if is_refund and not order.get('tenders'):
                    for r in returns:
                        sid = r.get('source_order_id')
                        if sid:
                            source_order_ids.add(sid)
        
        # Fetch Source Orders
        source_orders = []
        if source_order_ids:
            # batch_retrieve_orders must be implemented in square_client
            try:
                source_orders = self.sq.batch_retrieve_orders(list(source_order_ids))
            except Exception as e:
                print(f"Warning: Failed to batch retrieve source orders: {e}")
        
        # Build Tender Map from Source Orders
        tender_type_map = {} # (order_id, tender_id) -> type
        for so in source_orders:
            oid = so.get('id')
            for t in so.get('tenders', []):
                tid = t.get('id')
                ttype = t.get('type')
                if ttype == 'CARD':
                        brand = t.get('card_details', {}).get('card', {}).get('card_brand')
                        if brand == 'SQUARE_GIFT_CARD':
                            ttype = 'SQUARE_GIFT_CARD'
                tender_type_map[(oid, tid)] = ttype

        # Second Pass: Process properly
        for order in orders:
            # Common Data
            created_at = order.get('created_at', '')
            if created_at:
                try:
                    dt_utc = pd.to_datetime(created_at).to_pydatetime()
                    if dt_utc.tzinfo is None:
                        dt_utc = dt_utc.replace(tzinfo=pytz.UTC)
                except Exception as e:
                    print(f"Error parsing date {created_at}: {e}")
                    dt_utc = datetime.now(pytz.UTC)
 
                # Convert to Edmonton
                tz_edmonton = pytz.timezone('America/Edmonton')
                dt_local = dt_utc.astimezone(tz_edmonton)
                
                date_val = dt_local.strftime("%Y-%m-%d")
                time_val = dt_local.strftime("%H:%M:%S")
            else:
                date_val = ""
                time_val = ""

            # --- Financial Calculations ---
            sales_items = order.get('line_items', [])
            returns = order.get('returns', [])
            
            # Determine Event Type & Net Amounts
            net_amounts = order.get('net_amounts', {})
            net_total_money = float(net_amounts.get('total_money', {}).get('amount', 0))
            
            event_type = "Payment"
            if net_total_money < 0:
                event_type = "Refund"
            elif net_total_money == 0 and len(returns) > 0:
                event_type = "Refund"

            # Gross Sales Calculation (Sales Gross - Return Gross)
            s_gross = sum([float(l.get('gross_sales_money', {}).get('amount', 0)) for l in sales_items])
            r_gross = 0.0
            for r in returns:
                for rl in r.get('return_line_items', []):
                    r_gross += float(rl.get('gross_return_money', {}).get('amount', 0))
            
            net_gross_cents = s_gross - r_gross
            tx_gross_sales = net_gross_cents / 100.0
            
            # Discounts / Tax / Tip from Order Net Amounts
            # User requested values be negative -> -1 * Amount
            tx_discount = -float(net_amounts.get('discount_money', {}).get('amount', 0)) / 100.0
            
            tx_tax = float(net_amounts.get('tax_money', {}).get('amount', 0)) / 100.0
            tx_tip = float(net_amounts.get('tip_money', {}).get('amount', 0)) / 100.0
            tx_total_collected = float(net_amounts.get('total_money', {}).get('amount', 0)) / 100.0
            
            # Tenders
            tenders = order.get('tenders', [])
            cash_amt = 0.0
            gc_amt = 0.0
            entry_method = ""
            customer_name = order.get('ticket_name', '')
            
            if event_type == "Payment":
                for t in tenders:
                    amt = float(t.get('amount_money', {}).get('amount', 0)) / 100.0
                    t_type = t.get('type')
                    
                    if t_type == 'CASH':
                        cash_amt += amt
                    elif t_type == 'SQUARE_GIFT_CARD':
                        gc_amt += amt
                    elif t_type == 'CARD':
                        brand = t.get('card_details', {}).get('card', {}).get('card_brand')
                        if brand == 'SQUARE_GIFT_CARD':
                             gc_amt += amt
                        
                        if not entry_method:
                            entry_method = t.get('card_details', {}).get('entry_method', '')
            
            elif event_type == "Refund":
                if tenders:
                     for t in tenders:
                        amt = float(t.get('amount_money', {}).get('amount', 0)) / 100.0
                        t_type = t.get('type')
                        if t_type == 'CASH': cash_amt += amt
                        elif t_type == 'SQUARE_GIFT_CARD': gc_amt += amt
                else:
                    # Logic using Source Order Map
                    refunds_list = order.get('refunds', [])
                    for ref in refunds_list:
                         ref_amt = -float(ref.get('amount_money', {}).get('amount', 0)) / 100.0
                         tid = ref.get('tender_id')
                         
                         source_oid = None
                         if returns:
                             source_oid = returns[0].get('source_order_id')
                         
                         found_type = None
                         if source_oid and tid:
                             found_type = tender_type_map.get((source_oid, tid))
                         
                         if found_type == 'CASH':
                             cash_amt += ref_amt
                         elif found_type == 'SQUARE_GIFT_CARD':
                             gc_amt += ref_amt
                         elif not found_type:
                             # Fallback Heuristic
                             reason = ref.get('reason', '').lower()
                             if "change" in reason or "cash" in reason:
                                 cash_amt += ref_amt

            # Source
            source = order.get('source', {}).get('name', 'Square')
            
            # Build Transaction Row
            tx_row = []
            for col in tx_headers:
                col_lower = col.lower()
                val = ""
                
                if "date" in col_lower: val = date_val
                elif "time" in col_lower: val = time_val
                elif "timezone" in col_lower: val = "Mountain Time (US & Canada)"
                elif "gross" in col_lower and "sales" in col_lower: val = tx_gross_sales
                elif "discount" in col_lower: val = tx_discount
                # Net Sales = Gross + Discount (since Discount is negative)
                elif "net" in col_lower and "sales" in col_lower: val = tx_gross_sales + tx_discount
                elif "tax" in col_lower: val = tx_tax
                elif "tip" in col_lower: val = tx_tip
                elif "total collected" in col_lower or ("total" in col_lower and "ref" not in col_lower and "tax" not in col_lower): val = tx_total_collected
                elif "source" in col_lower: val = source
                elif "reference" in col_lower or "id" in col_lower: val = order.get('id')
                elif "description" in col_lower: 
                    token = order.get('id')[-4:]
                    val = f"Square Order {token}" if event_type == "Payment" else f"Square Refund {token}"
                
                # Dynamic Columns
                elif "event" in col_lower and "type" in col_lower: val = event_type
                elif ("card" in col_lower or "cash" in col_lower) and "entry" in col_lower: val = entry_method
                elif "cash" in col_lower and "entry" not in col_lower: val = cash_amt if cash_amt != 0 else 0
                elif "gift" in col_lower and "card" in col_lower: val = gc_amt if gc_amt != 0 else 0
                elif "customer" in col_lower and "name" in col_lower: val = customer_name
                
                tx_row.append(str(val) if val != "" else "")
            
            tx_rows.append(tx_row)
            
            # --- Item Level Rows ---
            for line in sales_items:
                self._add_item_row(item_rows, item_headers, line, date_val, time_val, order, is_return=False)

            for r in returns:
                for line in r.get('return_line_items', []):
                    self._add_item_row(item_rows, item_headers, line, date_val, time_val, order, is_return=True)
        
        return tx_rows, item_rows

    def _add_item_row(self, item_rows, item_headers, line, date_val, time_val, order, is_return=False):
        item_name = line.get('name', '')
        qty = float(line.get('quantity', 0))
        if is_return:
             qty = -qty
        
        # Money fields
        if is_return:
            gross_money = -float(line.get('gross_return_money', {}).get('amount', 0)) / 100.0
            tax_money = -float(line.get('total_tax_money', {}).get('amount', 0)) / 100.0
            # Refund Discount -> Positive
            disc_money = float(line.get('total_discount_money', {}).get('amount', 0)) / 100.0
        else:
            gross_money = float(line.get('gross_sales_money', {}).get('amount', 0)) / 100.0
            # Sales Discount -> Negative
            disc_money = -float(line.get('total_discount_money', {}).get('amount', 0)) / 100.0
            tax_money = float(line.get('total_tax_money', {}).get('amount', 0)) / 100.0

        # Base Price (Unit Price)
        base_price = float(line.get('base_price_money', {}).get('amount', 0)) / 100.0
        
        # Net Sales = Gross + Discount
        net_sales_item = gross_money + disc_money
        
        cat_id = line.get('catalog_object_id') 
        cat_name = self.catalog.get_category_for_item(cat_id) or "Uncategorized"
        
        item_row = []
        for col in item_headers:
            col_lower = col.lower()
            val = ""
            if "date" in col_lower: val = date_val
            elif "time" in col_lower: val = time_val
            elif "category" in col_lower: val = cat_name
            elif "item" in col_lower: val = item_name
            elif "qty" in col_lower or "quantity" in col_lower: val = qty
            elif "price" in col_lower or "unit" in col_lower: val = base_price
            elif "gross" in col_lower: val = gross_money
            elif "discount" in col_lower: val = disc_money
            elif "net" in col_lower: val = net_sales_item
            elif "tax" in col_lower: val = tax_money
            elif "modifier" in col_lower:
                mods = [m.get('name') for m in line.get('modifiers', [])]
                val = ", ".join(mods)
            elif "reference" in col_lower: val = order.get('id')
            
            item_row.append(str(val) if val != "" else "")
        
        item_rows.append(item_row)

    def run(self, start_date, end_date=None):
        if not end_date:
            end_date = start_date

        # 1. Get Headers
        try:
            ws_tx = self.sh.worksheet("transactions")
            tx_headers = ws_tx.row_values(1)
            print(f"Transactions Headers: {tx_headers}")

            ws_items = self.sh.worksheet("items")
            item_headers = ws_items.row_values(1)
            print(f"Items Headers: {item_headers}")
            
        except gspread.exceptions.WorksheetNotFound:
            print(f"Error: Required tabs 'transactions' or 'items' not found. Available tabs: {[idx.title for idx in self.sh.worksheets()]}")
            return

        # 2. Fetch Data
        print(f"Fetching Square data from {start_date} to {end_date}...")
        orders = self.sq.fetch_orders(start_date, end_date)
        print(f"Found {len(orders)} orders.")
        
        if not orders:
            print("No orders found.")
            return

        # 3. Process
        tx_rows, item_rows = self.process_orders(orders, tx_headers, item_headers)

        # 4. Append
        if tx_rows:
            print(f"Appending {len(tx_rows)} rows to Transactions...")
            ws_tx.append_rows(tx_rows)
        
        if item_rows:
            print(f"Appending {len(item_rows)} rows to Items...")
            ws_items.append_rows(item_rows)
            
        print("Export Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (Start Date)")
    parser.add_argument("--end-date", required=False, help="YYYY-MM-DD (End Date)")
    args = parser.parse_args()
    
    exporter = SquareToSheets()
    exporter.run(args.date, args.end_date)
