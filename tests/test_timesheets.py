"""
Workstream 4 tests: Square timecards -> payroll hours.

Offline: check worked-hours math (unpaid breaks subtracted, paid breaks kept),
per-employee aggregation, open-timecard skipping, and the worksheet render.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from timesheet_processor import (  # noqa: E402
    timecard_hours, aggregate, render_worksheet, _duration_seconds,
)


def tc(tid, mid, start, end, breaks=None, status="CLOSED"):
    return {"id": tid, "team_member_id": mid, "start_at": start, "end_at": end,
            "breaks": breaks or [], "status": status}


def brk(start, end, is_paid, expected=None):
    b = {"start_at": start, "end_at": end, "is_paid": is_paid}
    if expected:
        b["expected_duration"] = expected
    return b


def test_hours_simple():
    h = timecard_hours(tc("t1", "m1", "2026-07-27T09:00:00-06:00", "2026-07-27T17:00:00-06:00"))
    assert h == pytest.approx(8.0, abs=0.001)


def test_unpaid_break_subtracted_paid_kept():
    # 8h shift, 30m unpaid lunch -> 7.5h
    h = timecard_hours(tc("t2", "m1", "2026-07-27T09:00:00-06:00", "2026-07-27T17:00:00-06:00",
                          breaks=[brk("2026-07-27T12:00:00-06:00", "2026-07-27T12:30:00-06:00", False)]))
    assert h == pytest.approx(7.5, abs=0.001)
    # a PAID 15m break does not reduce hours
    h2 = timecard_hours(tc("t3", "m1", "2026-07-27T09:00:00-06:00", "2026-07-27T17:00:00-06:00",
                           breaks=[brk("2026-07-27T15:00:00-06:00", "2026-07-27T15:15:00-06:00", True)]))
    assert h2 == pytest.approx(8.0, abs=0.001)


def test_break_uses_expected_duration_when_no_end():
    h = timecard_hours(tc("t4", "m1", "2026-07-27T09:00:00-06:00", "2026-07-27T17:00:00-06:00",
                          breaks=[brk("2026-07-27T12:00:00-06:00", None, False, expected="PT1H")]))
    assert h == pytest.approx(7.0, abs=0.001)


def test_open_timecard_skipped():
    assert timecard_hours(tc("t5", "m1", "2026-07-27T09:00:00-06:00", None, status="OPEN")) is None


def test_iso_duration_parser():
    assert _duration_seconds("PT30M") == 1800
    assert _duration_seconds("PT1H30M") == 5400
    assert _duration_seconds("PT45M") == 2700
    assert _duration_seconds(None) == 0


def test_aggregate_per_employee_and_names():
    cards = [
        tc("a", "m1", "2026-07-27T09:00:00-06:00", "2026-07-27T17:00:00-06:00"),           # 8
        tc("b", "m1", "2026-07-28T09:00:00-06:00", "2026-07-28T13:00:00-06:00"),           # 4
        tc("c", "m2", "2026-07-27T10:00:00-06:00", "2026-07-27T15:00:00-06:00",
           breaks=[brk("2026-07-27T12:00:00-06:00", "2026-07-27T12:30:00-06:00", False)]), # 4.5
        tc("d", "m3", "2026-07-27T09:00:00-06:00", None, status="OPEN"),                    # skipped
    ]
    rows = aggregate(cards, {"m1": "Alice Ng", "m2": "Bob Lee"})
    by = {r["team_member_id"]: r for r in rows}
    assert by["m1"]["hours"] == pytest.approx(12.0, abs=0.001) and by["m1"]["shifts"] == 2
    assert by["m1"]["name"] == "Alice Ng"
    assert by["m2"]["hours"] == pytest.approx(4.5, abs=0.001)
    assert "m3" not in by  # open timecard skipped
    # sorted by name
    assert [r["name"] for r in rows] == ["Alice Ng", "Bob Lee"]


def test_render_worksheet_has_total():
    rows = aggregate(
        [tc("a", "m1", "2026-07-27T09:00:00-06:00", "2026-07-27T17:00:00-06:00")],
        {"m1": "Alice Ng"})
    text = "\n".join(render_worksheet(rows, "2026-07-27", "2026-08-09"))
    assert "Payroll hours worksheet" in text
    assert "Alice Ng" in text
    assert "TOTAL" in text
