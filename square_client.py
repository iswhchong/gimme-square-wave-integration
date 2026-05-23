import requests
import config
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    import pytz as ZoneInfo # fallback if somehow old python

class SquareClient:
    def __init__(self):
        if not config.SQUARE_ACCESS_TOKEN:
            raise ValueError("Square Access Token is missing")
        
        self.base_url = "https://connect.squareup.com/v2"
        self.headers = {
            "Authorization": f"Bearer {config.SQUARE_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Square-Version": "2024-01-18"
        }
        self.location_id = config.SQUARE_LOCATION_ID

    def fetch_orders(self, start_date_str, end_date_str):
        """
        Fetch orders for a date range.
        Dates should be in 'YYYY-MM-DD' format.
        """
        print(f"Fetching Square orders from {start_date_str} to {end_date_str}...")
        
        # Convert to ISO format with timezone (UTC is standard for API, but we'll use local day boundaries if possible)
        # Square SearchOrders expects RFC 3339 format
        try:
            tz = ZoneInfo("America/Edmonton")
        except TypeError:
            # If using pytz fallback
            import pytz
            tz = pytz.timezone("America/Edmonton")
            
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=tz)
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=tz)
        
        start_at = start_dt.isoformat()
        end_at = end_dt.isoformat()

        url = f"{self.base_url}/orders/search"
        
        all_orders = []
        cursor = None
        
        while True:
            payload = {
                "location_ids": [self.location_id],
                "query": {
                    "filter": {
                        "state_filter": {
                            "states": ["COMPLETED"]
                        },
                        "date_time_filter": {
                            "closed_at": {
                                "start_at": start_at,
                                "end_at": end_at
                            }
                        }
                    },
                    "sort": {
                        "sort_field": "CLOSED_AT",
                        "sort_order": "ASC"
                    }
                }
            }
            
            if cursor:
                payload["cursor"] = cursor
            
            response = requests.post(url, json=payload, headers=self.headers)
            
            if response.status_code != 200:
                print(f"Error fetching orders: {response.text}")
                response.raise_for_status()
                
            data = response.json()
            orders = data.get("orders", [])
            all_orders.extend(orders)
            
            cursor = data.get("cursor")
            if not cursor:
                break
                
        print(f"Total orders found: {len(all_orders)}")
        return all_orders

    def batch_retrieve_orders(self, order_ids):
        """
        Batch retrieve orders by ID.
        """
        if not order_ids:
            return []
            
        print(f"Batch retrieving {len(order_ids)} orders...")
        url = f"{self.base_url}/orders/batch-retrieve"
        
        all_orders = []
        # API limit is 100 per batch usually
        chunk_size = 100
        for i in range(0, len(order_ids), chunk_size):
            chunk = order_ids[i:i+chunk_size]
            payload = {
                "location_id": self.location_id,
                "order_ids": chunk
            }
            
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code != 200:
                print(f"Error batch retrieving: {response.text}")
                continue
                
            data = response.json()
            all_orders.extend(data.get("orders", []))
            
        return all_orders
