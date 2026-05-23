from square_client import SquareClient
import json

sq = SquareClient()
# Hardcoded order ID from user
order_id = "Pvm0uAltXayowX9iduDRhdgeV" 
# fetch_orders gets list, but we might need to query by ID or just filter from the day's pull.
# Let's try to fetch the specific order using valid python client methods if available, 
# or just fetch the day 2026-01-18 and filter.

# Dump wide range to catch both
orders = sq.fetch_orders("2026-01-03", "2026-01-06")
with open("orders_dump_refunds.json", "w") as f:
    json.dump(orders, f, indent=2)
print(f"Dumped {len(orders)} orders to orders_dump_refunds.json")

