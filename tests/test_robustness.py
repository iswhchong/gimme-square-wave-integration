"""
Phase 1 / Workstream 3 tests: robustness & correctness hardening.

  - http_util.post_with_retry: retries transient failures, honors a timeout,
    does NOT retry non-transient responses, and gives up after max_retries.
  - processor rounding: sub-tolerance gaps are absorbed (and logged); larger
    gaps raise ReconciliationError instead of silently moving dollars.
  - validation: net-refund days error, sales-without-tenders warn; malformed
    payloads are caught before any posting.

All offline; no network.
"""

import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import http_util  # noqa: E402
from errors import ReconciliationError  # noqa: E402
from processor import Processor  # noqa: E402
from validation import validate_summary, validate_payloads  # noqa: E402
from tests.fixtures import SYNTHETIC_CATALOG, ExplodingSquareClient  # noqa: E402


# --------------------------------------------------------------------------
# HTTP retry/backoff
# --------------------------------------------------------------------------

class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = f"status {status_code}"


def _no_sleep(_):
    pass


def test_retry_then_success_on_transient_status():
    calls = {"n": 0}

    def poster(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        return _Resp(503) if calls["n"] < 3 else _Resp(200)

    resp = http_util.post_with_retry("http://x", json={}, headers={},
                                     sleep=_no_sleep, poster=poster)
    assert resp.status_code == 200
    assert calls["n"] == 3  # two 503s then a 200


def test_retry_then_raise_on_persistent_transport_error():
    def poster(url, json=None, headers=None, timeout=None):
        raise requests.exceptions.ConnectionError("boom")

    with pytest.raises(requests.exceptions.ConnectionError):
        http_util.post_with_retry("http://x", json={}, headers={},
                                  max_retries=2, sleep=_no_sleep, poster=poster)


def test_non_transient_status_is_not_retried():
    calls = {"n": 0}

    def poster(url, json=None, headers=None, timeout=None):
        calls["n"] += 1
        return _Resp(400)  # client error: retrying won't help

    resp = http_util.post_with_retry("http://x", json={}, headers={},
                                     sleep=_no_sleep, poster=poster)
    assert resp.status_code == 400
    assert calls["n"] == 1  # tried exactly once


def test_timeout_is_passed_through():
    seen = {}

    def poster(url, json=None, headers=None, timeout=None):
        seen["timeout"] = timeout
        return _Resp(200)

    http_util.post_with_retry("http://x", timeout=7, sleep=_no_sleep, poster=poster)
    assert seen["timeout"] == 7


# --------------------------------------------------------------------------
# Rounding reconciliation
# --------------------------------------------------------------------------

def _summary(total_collected, gross_sales):
    """Minimal summary with a single sales account, no tax/tips/discounts."""
    acct = config.ITEM_CATEGORY_MAPPING["Drinks"]
    return {
        "date": "2026-05-23",
        "total_collected": total_collected,
        "sales_breakdown": {acct: gross_sales},
        "tax": 0.0,
        "tips": 0.0,
        "tenders": {"cash": total_collected, "gift_card": 0.0, "card": 0.0, "other": 0.0},
        "source_order_ids": ["ORDER_1"],
    }


def _proc():
    return Processor(catalog=SYNTHETIC_CATALOG, square_client=ExplodingSquareClient())


def test_subtolerance_gap_is_absorbed_into_largest_line():
    # collected 10.01 vs credits 10.00 -> +0.01 gap, within $0.05 tolerance.
    payloads = _proc().prepare_wave_transactions(_summary(10.01, 10.00))
    journal = next(p for p in payloads if p["role"] == "sales_journal")
    credits = sum(l["amount"] for l in journal["lines"])
    assert journal["amount"] == pytest.approx(10.01, abs=0.005)
    assert credits == pytest.approx(10.01, abs=0.005)  # adjustment applied


def test_over_tolerance_gap_raises_rather_than_fudging():
    # collected 10.50 vs credits 10.00 -> $0.50 gap, well over tolerance.
    with pytest.raises(ReconciliationError):
        _proc().prepare_wave_transactions(_summary(10.50, 10.00))


# --------------------------------------------------------------------------
# Input & payload validation
# --------------------------------------------------------------------------

def test_negative_net_day_is_an_error():
    errors, _ = validate_summary(_summary(-5.00, -5.00))
    assert any("Net-refund" in e for e in errors)


def test_sales_without_tenders_warns():
    s = _summary(10.00, 10.00)
    s["tenders"] = {"cash": 0.0, "gift_card": 0.0, "card": 0.0, "other": 0.0}
    errors, warnings = validate_summary(s)
    assert errors == []
    assert any("tenders net to $0.00" in w for w in warnings)


def test_validate_payloads_catches_malformed():
    bad = [
        {"role": "sales_journal", "date": "2026-05-23", "description": "x",
         "amount": -1.0, "lines": []},                       # negative amount + no lines
        {"role": "transfer_cash", "date": "2026-05-23", "description": "y",
         "amount": 5.0, "lines": [{"account_id": "", "direction": "SIDEWAYS", "amount": -2}]},
    ]
    errors = validate_payloads(bad)
    joined = " ".join(errors)
    assert "no line items" in joined
    assert "negative anchor amount" in joined
    assert "invalid direction" in joined
    assert "missing account_id" in joined


def test_validate_payloads_passes_clean_day():
    payloads = _proc().prepare_wave_transactions(_summary(10.00, 10.00))
    assert validate_payloads(payloads) == []
