"""
Compute payroll hours from Square timecards (Workstream 4).

Per timecard: worked hours = (end_at - start_at) minus any UNPAID breaks. Paid
breaks count as worked time. Open timecards (no end_at) are skipped with a warning.
Hours are aggregated per employee for the pay period into a worksheet Kent keys
into Wave Payroll (no Wave posting).
"""

import re
from datetime import datetime

from logging_setup import get_logger

logger = get_logger("timesheet_processor")

_ISO_DUR = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def _parse_ts(ts):
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _duration_seconds(iso):
    """Parse an ISO-8601 duration like 'PT30M' / 'PT1H30M' to seconds (0 if unparseable)."""
    if not iso:
        return 0
    m = _ISO_DUR.match(iso)
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _break_seconds(brk):
    """Seconds for a break: actual (end-start) if available, else expected_duration."""
    start, end = _parse_ts(brk.get("start_at")), _parse_ts(brk.get("end_at"))
    if start and end and end > start:
        return (end - start).total_seconds()
    return _duration_seconds(brk.get("expected_duration"))


def timecard_hours(tc):
    """Worked hours for one timecard, or None if it can't be computed (open/no end)."""
    start, end = _parse_ts(tc.get("start_at")), _parse_ts(tc.get("end_at"))
    if not start or not end or end <= start:
        logger.warning("Skipping timecard %s: missing/invalid end (status=%s).",
                       tc.get("id"), tc.get("status"))
        return None
    worked = (end - start).total_seconds()
    for brk in tc.get("breaks", []) or []:
        if not brk.get("is_paid", False):
            worked -= _break_seconds(brk)
    return max(worked, 0) / 3600.0


def aggregate(timecards, member_names=None):
    """
    Aggregate timecards -> list of per-employee dicts sorted by name:
      {team_member_id, name, hours, shifts}
    """
    member_names = member_names or {}
    by_member = {}
    skipped = 0
    for tc in timecards:
        hrs = timecard_hours(tc)
        if hrs is None:
            skipped += 1
            continue
        mid = tc.get("team_member_id")
        rec = by_member.setdefault(mid, {"team_member_id": mid,
                                         "name": member_names.get(mid, mid),
                                         "hours": 0.0, "shifts": 0})
        rec["hours"] += hrs
        rec["shifts"] += 1
    for rec in by_member.values():
        rec["hours"] = round(rec["hours"], 2)
    if skipped:
        logger.warning("%d timecard(s) skipped (open / no end time).", skipped)
    return sorted(by_member.values(), key=lambda r: r["name"].lower())


def render_worksheet(rows, start_date, end_date):
    """Human-readable payroll-hours worksheet for the pay period."""
    lines = [f"Payroll hours worksheet — pay period {start_date} to {end_date}", ""]
    if not rows:
        lines.append("  (no hours in this period)")
        return lines
    lines.append(f"  {'Employee':28} {'Hours':>8}  {'Shifts':>6}")
    lines.append(f"  {'-'*28} {'-'*8}  {'-'*6}")
    total_h = 0.0
    for r in rows:
        lines.append(f"  {r['name'][:28]:28} {r['hours']:>8.2f}  {r['shifts']:>6}")
        total_h += r["hours"]
    lines.append(f"  {'-'*28} {'-'*8}")
    lines.append(f"  {'TOTAL':28} {round(total_h,2):>8.2f}")
    return lines
