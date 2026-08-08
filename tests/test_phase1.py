"""
Phase 1 tests:
  1. Characterization — pin down the current aggregation & payload math so future
     hardening cannot silently change the accounting.
  2. Idempotency — deterministic ids, content hashing, ledger, and the posting guard
     that guarantees re-runs don't double-post.

All offline: a fake catalog and a fake Wave client; no network, no live tokens.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
from processor import Processor  # noqa: E402
from idempotency import deterministic_external_id, content_hash, PostedLedger  # noqa: E402
import main  # noqa: E402
from tests.fixtures import (  # noqa: E402
    SYNTHETIC_CATALOG,
    ExplodingSquareClient,
    synthetic_single_day,
)

CENTS = 0.005  # tolerance for float money comparisons


# ---------------------------------------------------------------------------
# 1. Characterization of the accounting math
# ---------------------------------------------------------------------------

def _processor():
    return Processor(catalog=SYNTHETIC_CATALOG, square_client=ExplodingSquareClient())


def test_aggregate_totals_match_source():
    proc = _processor()
    summary = proc.aggregate_daily_orders(synthetic_single_day(), "2026-05-23")

    assert summary["total_collected"] == pytest.approx(33.50, abs=CENTS)
    assert summary["tax"] == pytest.approx(1.50, abs=CENTS)
    assert summary["tips"] == pytest.approx(2.00, abs=CENTS)
    assert summary["tenders"]["cash"] == pytest.approx(13.50, abs=CENTS)
    assert summary["tenders"]["card"] == pytest.approx(20.00, abs=CENTS)
    assert summary["tenders"]["gift_card"] == pytest.approx(0.00, abs=CENTS)

    drinks = config.ITEM_CATEGORY_MAPPING["Drinks"]
    food = config.ITEM_CATEGORY_MAPPING["Food & Snack"]
    assert summary["sales_breakdown"][drinks] == pytest.approx(10.00, abs=CENTS)
    assert summary["sales_breakdown"][food] == pytest.approx(20.00, abs=CENTS)


def test_sales_journal_is_balanced_double_entry():
    """Anchor (net collected) must equal credits minus contra-debits — the core
    double-entry invariant. If this ever breaks, the books won't balance."""
    proc = _processor()
    summary = proc.aggregate_daily_orders(synthetic_single_day(), "2026-05-23")
    payloads = proc.prepare_wave_transactions(summary)

    journal = next(p for p in payloads if p["role"] == "sales_journal")
    credits = sum(l["amount"] for l in journal["lines"] if l["direction"] == "INCREASE")
    # In this fixture all lines are INCREASE credits (no discounts), so anchor == credits.
    assert journal["amount"] == pytest.approx(credits, abs=CENTS)
    assert journal["amount"] == pytest.approx(33.50, abs=CENTS)


def test_cash_transfer_present_giftcard_absent():
    proc = _processor()
    summary = proc.aggregate_daily_orders(synthetic_single_day(), "2026-05-23")
    payloads = proc.prepare_wave_transactions(summary)
    roles = {p["role"] for p in payloads}
    assert "transfer_cash" in roles
    assert "transfer_gift_card" not in roles  # no gift-card tender in fixture


# ---------------------------------------------------------------------------
# 2. Idempotency primitives
# ---------------------------------------------------------------------------

def test_external_id_is_deterministic_and_role_specific():
    a = deterministic_external_id("sales_journal", "LOC9", "2026-05-23")
    b = deterministic_external_id("sales_journal", "LOC9", "2026-05-23")
    c = deterministic_external_id("transfer_cash", "LOC9", "2026-05-23")
    assert a == b == "SQ_SALES_JOURNAL_LOC9_20260523"
    assert a != c  # different roles -> different ids, same day


def test_content_hash_changes_when_amount_changes():
    p1 = {"role": "sales_journal", "date": "2026-05-23", "amount": 33.50,
          "lines": [{"account_id": "X", "direction": "INCREASE", "amount": 33.50}]}
    p2 = dict(p1, amount=40.00,
              lines=[{"account_id": "X", "direction": "INCREASE", "amount": 40.00}])
    assert content_hash(p1) == content_hash(dict(p1))  # stable
    assert content_hash(p1) != content_hash(p2)         # sensitive to change


def test_ledger_persists_and_finds(tmp_path):
    path = str(tmp_path / "ledger.jsonl")
    ledger = PostedLedger(path)
    assert ledger.find("SQ_X") is None
    ledger.record("SQ_X", "hash1", 33.50, "WAVE_TX_1")

    reloaded = PostedLedger(path)  # survives process restart
    entry = reloaded.find("SQ_X")
    assert entry["wave_transaction_id"] == "WAVE_TX_1"
    assert entry["content_hash"] == "hash1"


# ---------------------------------------------------------------------------
# 3. The posting guard: post once, skip on re-run, flag changes
# ---------------------------------------------------------------------------

class FakeWave:
    def __init__(self):
        self.calls = []

    def create_transaction(self, date_str, description, amount, line_items,
                           external_id=None, anchor_direction="DEPOSIT",
                           anchor_account_id=None):
        self.calls.append(external_id)
        return f"WAVE_TX_{len(self.calls)}"


def _payload():
    return {
        "role": "sales_journal", "date": "2026-05-23",
        "description": "Sales - May 23 - Square", "amount": 33.50,
        "lines": [{"account_id": "X", "direction": "INCREASE", "amount": 33.50}],
    }


def test_first_run_posts_second_run_skips(tmp_path):
    wv = FakeWave()
    ledger = PostedLedger(str(tmp_path / "l.jsonl"))

    r1 = main._post_payload_idempotent(wv, _payload(), ledger)
    assert r1 == "posted"
    assert len(wv.calls) == 1

    # Re-run same day, same numbers: must NOT post again.
    ledger2 = PostedLedger(str(tmp_path / "l.jsonl"))
    r2 = main._post_payload_idempotent(wv, _payload(), ledger2)
    assert r2 == "skipped_duplicate"
    assert len(wv.calls) == 1  # no second Wave call


def test_changed_amount_is_flagged_not_double_posted(tmp_path):
    wv = FakeWave()
    ledger = PostedLedger(str(tmp_path / "l.jsonl"))
    main._post_payload_idempotent(wv, _payload(), ledger)

    changed = dict(_payload(), amount=40.00,
                   lines=[{"account_id": "X", "direction": "INCREASE", "amount": 40.00}])
    ledger2 = PostedLedger(str(tmp_path / "l.jsonl"))
    r = main._post_payload_idempotent(wv, changed, ledger2)
    assert r == "skipped_changed"
    assert len(wv.calls) == 1  # refused to post the changed version

    # With --replace it supersedes.
    ledger3 = PostedLedger(str(tmp_path / "l.jsonl"))
    r2 = main._post_payload_idempotent(wv, changed, ledger3, replace=True)
    assert r2 == "posted"
    assert len(wv.calls) == 2


def test_same_external_id_used_across_runs(tmp_path):
    wv = FakeWave()
    ledger = PostedLedger(str(tmp_path / "l.jsonl"))
    main._post_payload_idempotent(wv, _payload(), ledger)
    expected = deterministic_external_id("sales_journal", config.SQUARE_LOCATION_ID, "2026-05-23")
    assert wv.calls[0] == expected


# ---------------------------------------------------------------------------
# 4. wave_client fallback external id must be deterministic (no datetime.now)
# ---------------------------------------------------------------------------

def test_wave_client_fallback_external_id_is_deterministic(monkeypatch):
    import wave_client

    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"data": {"moneyTransactionCreate": {
                "didSucceed": True, "transaction": {"id": "TX"}}}}

    def fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        captured.setdefault("external_ids", []).append(
            json["variables"]["input"]["externalId"])
        return FakeResp()

    monkeypatch.setattr(wave_client.config, "WAVE_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(wave_client.config, "WAVE_BUSINESS_ID", "biz")
    monkeypatch.setattr(wave_client.requests, "post", fake_post)

    wv = wave_client.WaveClient()
    lines = [{"account_id": "A", "amount": 10.0, "direction": "INCREASE"}]
    # Two posts, no explicit external_id, identical content:
    wv.create_transaction("2026-05-23", "Sales", 10.0, lines)
    wv.create_transaction("2026-05-23", "Sales", 10.0, lines)

    ids = captured["external_ids"]
    assert ids[0] == ids[1]              # deterministic, not timestamp-based
    assert ids[0].startswith("SQ_")
