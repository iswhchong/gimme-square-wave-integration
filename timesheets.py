r"""
Square Team timecards -> payroll-hours worksheet (Workstream 4).

Pulls Square timecards for a bi-weekly pay period, sums worked hours per employee
(minus unpaid breaks), and writes a worksheet Kent keys into Wave Payroll. This is
READ-ONLY — it posts nothing to Wave.

Usage:
  python timesheets.py --start 2026-07-27 --end 2026-08-09
  python timesheets.py --start 2026-07-27                 # end defaults to start + 13 days (bi-weekly)
  python timesheets.py --start 2026-07-27 --dump          # also save raw timecards JSON

Writes logs/timesheet_<start>_<end>.txt. Requires the Square token to have the
TIMECARDS_READ permission.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from labor_client import LaborClient
from logging_setup import setup_logging, get_logger
from timesheet_processor import aggregate, render_worksheet

logger = get_logger()

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def _default_end(start_date):
    d = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=13)  # 14-day bi-weekly period
    return d.strftime("%Y-%m-%d")


def run(start_date, end_date, out_path=None, dump=False):
    client = LaborClient()
    timecards = client.search_timecards(start_date, end_date)
    names = client.list_team_members()
    rows = aggregate(timecards, names)

    lines = render_worksheet(rows, start_date, end_date)
    for line in lines:
        logger.info(line)

    out_path = out_path or os.path.join("logs", f"timesheet_{start_date}_{end_date}.txt")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Worksheet written -> %s", out_path)

    if dump:
        dump_path = os.path.join("logs", f"timecards_{start_date}_{end_date}.json")
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump({"timecards": timecards, "team_members": names}, f, indent=2)
        logger.info("Raw timecards dumped -> %s", dump_path)

    return EXIT_OK


def main():
    ap = argparse.ArgumentParser(description="Square timecards -> payroll hours worksheet")
    ap.add_argument("--start", help="Pay-period start YYYY-MM-DD.")
    ap.add_argument("--end", help="Pay-period end YYYY-MM-DD (default: start + 13 days).")
    ap.add_argument("--out", default=None, help="Worksheet output path.")
    ap.add_argument("--dump", action="store_true", help="Also save raw timecards JSON.")
    args = ap.parse_args()

    log_path = setup_logging()
    if not args.start:
        logger.error("--start is required.")
        return EXIT_USAGE
    start = args.start
    end = args.end or _default_end(start)
    logger.info("Timesheet run: pay period %s .. %s", start, end)

    try:
        code = run(start, end, out_path=args.out, dump=args.dump)
    except Exception as e:
        logger.exception("Timesheet run failed for %s..%s: %s", start, end, e)
        code = EXIT_FAILURE

    logger.info("Run log written to %s (exit=%d)", log_path, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
