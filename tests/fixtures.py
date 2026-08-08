"""
Test fixtures. The synthetic order below matches the shape of the Square Orders
Search API as read by processor.aggregate_daily_orders. To run these tests against
REAL captured data instead, drop your `orders_dump_*.json` and `square_catalog_full.json`
in the repo root and load them here (see load_real_dump()).
"""

import json
import os


class FakeCatalog:
    """Stand-in for CatalogManager: maps catalog_object_id -> category name."""

    def __init__(self, mapping):
        self._mapping = mapping

    def get_category_for_item(self, item_id):
        return self._mapping.get(item_id, "Uncategorized")


class ExplodingSquareClient:
    """Injected to prove aggregate_daily_orders makes NO Square calls on a
    tender-complete day (no refund source lookups needed)."""

    def batch_retrieve_orders(self, order_ids):
        raise AssertionError("SquareClient should not be called for this fixture")


# Category -> catalog_object_id used by the synthetic order.
SYNTHETIC_CATALOG = FakeCatalog({
    "VAR_DRINK": "Drinks",
    "VAR_FOOD": "Food & Snack",
})


def synthetic_single_day():
    """
    One clean completed order for 2026-05-23:
      Gross sales $30.00  (Drinks $10.00 + Food & Snack $20.00)
      Tax          $1.50
      Tip          $2.00
      Total       $33.50  (Cash $13.50 + Card $20.00)
      No discounts, no refunds.
    """
    return [
        {
            "id": "ORDER_1",
            "state": "COMPLETED",
            "net_amounts": {
                "total_money": {"amount": 3350, "currency": "CAD"},
                "tax_money": {"amount": 150, "currency": "CAD"},
                "tip_money": {"amount": 200, "currency": "CAD"},
                "discount_money": {"amount": 0, "currency": "CAD"},
            },
            "line_items": [
                {"name": "Cola", "catalog_object_id": "VAR_DRINK",
                 "gross_sales_money": {"amount": 1000, "currency": "CAD"}},
                {"name": "Burger", "catalog_object_id": "VAR_FOOD",
                 "gross_sales_money": {"amount": 2000, "currency": "CAD"}},
            ],
            "returns": [],
            "tenders": [
                {"id": "T_CASH", "type": "CASH",
                 "amount_money": {"amount": 1350, "currency": "CAD"}},
                {"id": "T_CARD", "type": "CARD",
                 "amount_money": {"amount": 2000, "currency": "CAD"},
                 "card_details": {"card": {"card_brand": "VISA"}}},
            ],
            "refunds": [],
            "discounts": [],
        }
    ]


def load_real_dump(orders_path, catalog_path):
    """Helper for when the real captured data is available."""
    with open(orders_path) as f:
        orders = json.load(f)
    from catalog_manager import CatalogManager
    catalog = CatalogManager(catalog_path) if os.path.exists(catalog_path) else None
    return orders, catalog
