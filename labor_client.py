"""
Square Labor + Team API client (Workstream 4).

Reads Timecards (clock in/out) and Team member names for payroll prep. Read-only.
Uses the newer Timecards API (the Shifts API retired 2026-05-21), which requires
Square-Version 2026-07-15 and the TIMECARDS_READ permission.
"""

import config
from http_util import post_with_retry
from logging_setup import get_logger

logger = get_logger("labor_client")

LABOR_VERSION = "2026-07-15"   # Timecards API (Shifts API is retired)


class LaborClient:
    def __init__(self):
        if not config.SQUARE_ACCESS_TOKEN:
            raise ValueError("Square Access Token is missing")
        self.base_url = "https://connect.squareup.com/v2"
        self.location_id = config.SQUARE_LOCATION_ID
        self.headers = {
            "Authorization": f"Bearer {config.SQUARE_ACCESS_TOKEN}",
            "Content-Type": "application/json",
            "Square-Version": LABOR_VERSION,
        }

    def search_timecards(self, start_date, end_date):
        """
        All CLOSED+OPEN timecards whose workday falls in [start_date, end_date]
        (inclusive), Edmonton timezone. Dates are 'YYYY-MM-DD'. Paginated.
        """
        url = f"{self.base_url}/labor/timecards/search"
        body = {
            "query": {
                "filter": {
                    "location_ids": [self.location_id] if self.location_id else None,
                    "workday": {
                        "date_range": {"start_date": start_date, "end_date": end_date},
                        "match_timecards_by": "START_AT",
                        "default_timezone": "America/Edmonton",
                    },
                },
                "sort": {"field": "START_AT", "order": "ASC"},
            },
            "limit": 200,
        }
        # Drop the null location filter if we have no location id.
        if not self.location_id:
            body["query"]["filter"].pop("location_ids", None)

        out, cursor = [], None
        logger.info("Searching timecards %s..%s", start_date, end_date)
        while True:
            if cursor:
                body["cursor"] = cursor
            resp = post_with_retry(url, json=body, headers=self.headers)
            if resp.status_code != 200:
                logger.error("Timecards search failed (%s): %s", resp.status_code, resp.text)
                resp.raise_for_status()
            data = resp.json()
            out.extend(data.get("timecards", []))
            cursor = data.get("cursor")
            if not cursor:
                break
        logger.info("Found %d timecard(s).", len(out))
        return out

    def list_team_members(self):
        """Return {team_member_id: 'Given Family'} for all team members."""
        url = f"{self.base_url}/team-members/search"
        members, cursor = {}, None
        while True:
            body = {"limit": 200}
            if cursor:
                body["cursor"] = cursor
            resp = post_with_retry(url, json=body, headers=self.headers)
            if resp.status_code != 200:
                logger.error("Team member search failed (%s): %s", resp.status_code, resp.text)
                resp.raise_for_status()
            data = resp.json()
            for tm in data.get("team_members", []):
                name = " ".join(x for x in [tm.get("given_name"), tm.get("family_name")] if x).strip()
                members[tm.get("id")] = name or tm.get("id")
            cursor = data.get("cursor")
            if not cursor:
                break
        logger.info("Loaded %d team member(s).", len(members))
        return members
