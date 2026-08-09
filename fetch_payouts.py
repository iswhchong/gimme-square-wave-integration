"""
Capture Square payouts + their entries for a date range, to a JSON file.

Workstream 2, step 1. This is a *read-only* helper: it pulls real payout data so
we can build the Square-Payouts -> Wave mapping and tests against real API shapes
(the same fixture-first approach used for orders in Phase 1). It posts nothing to
Wave and writes nothing to Square.

Usage (run locally, where your .env credentials live):

    python fetch_payouts.py --start 2026-07-27 --end 2026-08-09
    python fetch_payouts.py --start 2026-08-01 --end 2026-08-08 --out payouts_dump.json

Output:
  - <out> (default payouts_dump.json): [{ "payout": {...}, "entries": [...] }, ...]
  - a human-readable summary to the console, including the computed
    gross / fees / net per payout and whether net == amount_money.

Review the dump before sharing it: it contains payout amounts and a masked
destination (e.g. bank/card last 4). It does NOT contain your API token.
"""

import argparse
import json
import sys
import time

import requests

import config

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from datetime import datetime

BASE_URL = "https://connect.squareup.com/v2"
SQUARE_VERSION = "2024-01-18"
TIMEOUT = 30
MAX_RETRIES = 3
RETRYABLE = {429, 500, 502, 503, 504}


def _headers():
    if not config.SQUARE_ACCESS_TOKEN:
        raise SystemExit("SQUARE_ACCESS_TOKEN missing (check your .env).")
    return {
        "Authorization": f"Bearer {config.SQUARE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Square-Version": SQUARE_VERSION,
    }


def _edmonton():
    if ZoneInfo is not None:
        return ZoneInfo("America/Edmonton")
    import pytz
    return pytz.timezone("America/Edmonton")


def _get(url, params):
    """GET with a timeout and simple bounded backoff on transient failures."""
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = requests.get(url, headers=_headers(), params=params, timeout=TIMEOUT)
        except requests.exceptions.RequestException as e:
            if attempt > MAX_RETRIES:
                raise
            time.sleep(1.0 * (2 ** (attempt - 1)))
            continue
        if resp.status_code in RETRYABLE and attempt <= MAX_RETRIES:
            time.sleep(1.0 * (2 ** (attempt - 1)))
            continue
        if resp.status_code != 200:
            raise SystemExit(f"HTTP {resp.status_code} from {url}: {resp.text}")
        return resp.json()


def list_payouts(start_date, end_date):
    tz = _edmonton()
    begin = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz).isoformat()
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=tz).isoformat()

    payouts, cursor = [], None
    while True:
        params = {
            "location_id": config.SQUARE_LOCATION_ID,
            "begin_time": begin,
            "end_time": end,
            "sort_order": "ASC",
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor
        data = _get(f"{BASE_URL}/payouts", params)
        payouts.extend(data.get("payouts", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return payouts


def list_entries(payout_id):
    entries, cursor = [], None
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        data = _get(f"{BASE_URL}/payouts/{payout_id}/payout-entries", params)
        entries.extend(data.get("payout_entries", []))
        cursor = data.get("cursor")
        if not cursor:
            break
    return entries


def _cents(money):
    return int((money or {}).get("amount", 0))


def _fmt(cents):
    return f"${cents/100:,.2f}"


def main():
    ap = argparse.ArgumentParser(description="Capture Square payouts + entries to JSON.")
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD (Edmonton).")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD (Edmonton).")
    ap.add_argument("--out", default="payouts_dump.json", help="Output JSON path.")
    args = ap.parse_args()

    payouts = list_payouts(args.start, args.end)
    print(f"Found {len(payouts)} payout(s) from {args.start} to {args.end}.\n")

    dump = []
    entry_types = {}
    for p in payouts:
        pid = p.get("id")
        entries = list_entries(pid)
        dump.append({"payout": p, "entries": entries})

        gross = sum(_cents(e.get("gross_amount_money")) for e in entries)
        fees = sum(_cents(e.get("fee_amount_money")) for e in entries)
        net = sum(_cents(e.get("net_amount_money")) for e in entries)
        stated = _cents(p.get("amount_money"))
        for e in entries:
            entry_types[e.get("type")] = entry_types.get(e.get("type"), 0) + 1

        recon = "OK" if net == stated else f"MISMATCH (entries net {_fmt(net)} vs payout {_fmt(stated)})"
        print(f"- {pid}")
        print(f"    created_at : {p.get('created_at')}   status: {p.get('status')}")
        print(f"    arrival    : {p.get('arrival_date')}")
        print(f"    amount     : {_fmt(stated)}   ({len(entries)} entries)")
        print(f"    gross={_fmt(gross)}  fees={_fmt(fees)}  net={_fmt(net)}  reconcile: {recon}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2)
    print(f"\nEntry types seen: {entry_types or '{}'}")
    print(f"Wrote {len(dump)} payout(s) -> {args.out}")
    print("Review the file before sharing (it contains amounts + masked destination).")


if __name__ == "__main__":
    main()
