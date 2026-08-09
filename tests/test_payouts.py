"""
Workstream 2 tests: Square Payouts -> Wave (API posting via a suspense account).

Offline, against fixtures shaped like the real Payouts API dump. The transfer
line posts to a SUSPENSE account (Kent re-points it in Wave); fees + GST post
correctly. Checks the mapping balances, idempotency (SQ_PAYOUT_<id>), and the gate.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import main  # noqa: E402
import approval  # noqa: E402
import payouts  # noqa: E402
from payout_processor import PayoutProcessor  # noqa: E402
from validation import validate_payloads  # noqa: E402
from idempotency import PostedLedger  # noqa: E402
from errors import ReconciliationError  # noqa: E402


def money(c):
    return {"amount": c, "currency_code": "CAD"}


def charge(gross_c, fee_c):
    return {"type": "CHARGE", "gross_amount_money": money(gross_c),
            "fee_amount_money": money(fee_c), "net_amount_money": money(gross_c - fee_c),
            "type_charge_details": {"payment_id": "pay_x"}}


def other(gross_c):
    return {"type": "OTHER", "gross_amount_money": money(gross_c),
            "fee_amount_money": money(0), "net_amount_money": money(gross_c)}


def tax_on_fee(gross_c):
    return {"type": "TAX_ON_FEE", "gross_amount_money": money(gross_c),
            "fee_amount_money": money(0), "net_amount_money": money(gross_c),
            "type_tax_on_fee_details": {"tax_rate_description": "GST"}}


def payout(pid, entries, status="PAID", created="2026-07-14T02:05:19Z", arrival="2026-07-14"):
    net = sum(e["net_amount_money"]["amount"] for e in entries)
    return {"id": pid, "status": status, "amount_money": money(net),
            "created_at": created, "arrival_date": arrival, "type": "BATCH", "version": 1}


def _proc():
    return PayoutProcessor()


ACCT = config.PAYOUT_ACCOUNTS


def _by_acct(payload):
    return {l["account_id"]: l for l in payload["lines"]}


def _balances(payload):
    """Anchor deposit + expense/ITC debits should equal the suspense credit."""
    debits = payload["amount"]
    credit = 0.0
    for l in payload["lines"]:
        if l["account_id"] == ACCT["suspense"]:
            credit += l["amount"]
        else:
            debits += l["amount"]
    return round(debits, 2), round(credit, 2)


def test_maps_to_suspense_and_balances():
    # Reproduces Kent's Jul 13: net 900.49, transfer 916.82, cc 13.33, gift 2.86 + GST 0.14
    es = [charge(91682, 1333), other(-286), tax_on_fee(-14)]
    p = _proc().build_payload(payout("po_1", es), es)
    assert p["external_id"] == "SQ_PAYOUT_po_1"
    assert p["anchor_id"] == ACCT["bank"] and p["anchor_direction"] == "DEPOSIT"
    assert p["amount"] == pytest.approx(900.49, abs=0.005)
    assert p["date"] == "2026-07-14"                       # arrival/settlement
    assert p["description"] == "Jul 13 - Square Transfer"   # transfer date
    lines = _by_acct(p)
    assert lines[ACCT["suspense"]]["amount"] == pytest.approx(916.82, abs=0.005)
    assert lines[ACCT["suspense"]]["direction"] == "INCREASE"
    assert lines[ACCT["cc_fee"]]["amount"] == pytest.approx(13.33, abs=0.005)
    assert lines[ACCT["gift_card_fee"]]["amount"] == pytest.approx(2.86, abs=0.005)
    assert lines[ACCT["itc"]]["amount"] == pytest.approx(0.14, abs=0.005)
    debits, credit = _balances(p)
    assert debits == credit == pytest.approx(916.82, abs=0.005)


def test_card_only_has_no_gift_or_itc_lines():
    es = [charge(6853, 58), charge(1039, 15)]
    p = _proc().build_payload(payout("po_c", es), es)
    lines = _by_acct(p)
    assert ACCT["gift_card_fee"] not in lines
    assert ACCT["itc"] not in lines
    debits, credit = _balances(p)
    assert debits == credit


def test_reconciliation_mismatch_raises():
    es = [charge(1000, 20)]
    bad = payout("po_bad", es)
    bad["amount_money"] = money(9999)
    with pytest.raises(ReconciliationError):
        _proc().build_payload(bad, es)


def test_failed_payout_skipped():
    es = [charge(1000, 20)]
    assert _proc().build_payload(payout("po_f", es, status="FAILED"), es) is None


def test_payout_payload_passes_validation():
    es = [charge(91682, 1333), other(-286), tax_on_fee(-14)]
    p = _proc().build_payload(payout("po_v", es), es)
    assert validate_payloads([p]) == []


class FakeWave:
    def __init__(self):
        self.calls = []

    def create_transaction(self, **k):
        self.calls.append(k.get("external_id"))
        return f"WAVE_TX_{len(self.calls)}"


def test_idempotent_post_then_skip(tmp_path):
    es = [charge(1000, 22)]
    p = _proc().build_payload(payout("po_idem", es), es)
    wv = FakeWave()
    ledger = PostedLedger(str(tmp_path / "l.jsonl"))
    assert main._post_payload_idempotent(wv, p, ledger) == "posted"
    assert wv.calls == ["SQ_PAYOUT_po_idem"]
    ledger2 = PostedLedger(str(tmp_path / "l.jsonl"))
    assert main._post_payload_idempotent(wv, p, ledger2) == "skipped_duplicate"
    assert len(wv.calls) == 1


def test_approval_gate(tmp_path):
    es = [charge(91682, 1333), other(-286), tax_on_fee(-14)]
    p = _proc().build_payload(payout("po_gate", es), es)
    art = payouts.build_artifact("2026-07-13", "2026-07-13", [p])
    wv = FakeWave()
    ledger = PostedLedger(str(tmp_path / "l.jsonl"))
    assert main.post_approved(wv, art, ledger) is None      # unapproved -> refused
    assert wv.calls == []
    ok, _, art = approval.approve(art, "kent")
    assert ok
    outcomes = main.post_approved(wv, art, ledger)
    assert outcomes.get("posted") == 1
    assert wv.calls == ["SQ_PAYOUT_po_gate"]
