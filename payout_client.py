"""
Square Payouts API client (Workstream 2).

Reads payouts (Square Dashboard: Money -> Transfers) and their entries. These are
the bank transfers Kent records manually in Wave as "<Date> - Square Transfer".

Read-only: this never writes to Square. Uses the same auth/config and the shared
retry/timeout helper as the rest of the pipeline.
"""

from datetime import datetime

import config
from http_util import get_with_retry
from logging_setup import get_logger

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

logger = get_logger("payout_client")


class PayoutClient:
    def __init__(self):
        if not config.SQUARE_ACCESS_TOKEN:
            raise ValueError("Square Access Token is missing")
        self.base_url = "https://connect.squareup.com/v2"
        self.headers = {
            "Authorization": f"Bearer {config.SQUARE_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Square-Version": "2024-01-18",
        }
        self.location_id = config.SQUARE_LOCATION_ID

    @staticmethod
    def _tz():
        if ZoneInfo is not None:
            return ZoneInfo("America/Edmonton")
        import pytz
        return pytz.timezone("America/Edmonton")

    def list_payouts(self, start_date_str, end_date_str):
        """
        List payouts whose created_at falls within [start, end] (inclusive),
        using America/Edmonton day boundaries. Paginated. Returns raw payout dicts.
        """
        tz = self._tz()
        begin = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=tz).isoformat()
        end = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=tz).isoformat()

        logger.info("Fetching Square payouts %s..%s", start_date_str, end_date_str)
        payouts, cursor = [], None
        while True:
            params = {
                "location_id": self.location_id,
                "begin_time": begin,
                "end_time": end,
                "sort_order": "ASC",
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor
            resp = get_with_retry(f"{self.base_url}/payouts", params=params, headers=self.headers)
            if resp.status_code != 200:
                logger.error("Error listing payouts (%s): %s", resp.status_code, resp.text)
                resp.raise_for_status()
            data = resp.json()
            payouts.extend(data.get("payouts", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        logger.info("Found %d payout(s).", len(payouts))
        return payouts

    def list_payout_entries(self, payout_id):
        """List all entries for a payout (paginated). Returns raw entry dicts."""
        entries, cursor = [], None
        while True:
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            resp = get_with_retry(f"{self.base_url}/payouts/{payout_id}/payout-entries",
                                  params=params, headers=self.headers)
            if resp.status_code != 200:
                logger.error("Error listing entries for %s (%s): %s",
                             payout_id, resp.status_code, resp.text)
                resp.raise_for_status()
            data = resp.json()
            entries.extend(data.get("payout_entries", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        return entries

    def fetch_payouts_with_entries(self, start_date_str, end_date_str):
        """Convenience: list payouts in range, each paired with its entries."""
        out = []
        for p in self.list_payouts(start_date_str, end_date_str):
            out.append({"payout": p, "entries": self.list_payout_entries(p["id"])})
        return out
