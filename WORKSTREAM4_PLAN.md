# Workstream 4 — Staff timesheets (Square Team) → Wave payroll prep

**Goal:** turn Square Team clock in/out into a per-employee **hours worksheet** for a
bi-weekly pay period, which Kent keys into **Wave Payroll**. Read-only — it posts
nothing to Wave (Wave Payroll has no public timesheet API).

## Source
Square **Labor / Timecards API** (`POST /v2/labor/timecards/search`, Square-Version
`2026-07-15`, permission `TIMECARDS_READ`) — the Shifts API retired 2026-05-21.
Employee names come from the **Team API** (`/v2/team-members/search`).

## Hours math
Per timecard: worked hours = (end_at − start_at) − **unpaid** breaks (paid breaks
count). Open/unfinished timecards are skipped with a warning. Aggregated per
employee for the period. Decision: **total hours only** (no overtime split).

## Deliverable
`logs/timesheet_<start>_<end>.txt` — employee, total hours, shift count, and a grand
total. Kent enters these into Wave Payroll.

## Usage (run per pay period; NOT part of the daily job)
    python timesheets.py --start 2026-07-27 --end 2026-08-09
    python timesheets.py --start 2026-07-27            # end defaults to +13 days (bi-weekly)
    python timesheets.py --start 2026-07-27 --dump     # also save raw timecards JSON

## Files
labor_client.py (Timecards + Team), timesheet_processor.py (hours math + aggregate
+ worksheet), timesheets.py (entrypoint), tests/test_timesheets.py.

## Pending / to confirm live
- Square token must have TIMECARDS_READ (may need to add the scope + re-authorize).
- Run one recent completed bi-weekly period; eyeball hours vs Square; confirm break
  handling (paid vs unpaid) matches expectation.
