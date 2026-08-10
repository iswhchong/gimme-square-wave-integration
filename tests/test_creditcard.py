"""
Workstream 3 tests: CIBC credit-card spending -> Wave.

Offline: parse a CIBC-shaped CSV, categorize via the merchant rules, and check the
Wave payloads (charge/refund/payment directions, idempotent ids, the unconfigured-
account guard). No network.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import creditcard  # noqa: E402
from cibc_statement import parse_statement  # noqa: E402
from cc_processor import CreditCardProcessor  # noqa: E402
from validation import validate_payloads  # noqa: E402
from errors import ValidationError  # noqa: E402

# Dummy account map so tests don't depend on the real (or TODO) ids.
ACCT = {
    "card": "CARD", "alcohol": "ALC", "subscription": "SUB", "advertising": "ADV",
    "telephone_wireless": "TEL", "computer_internet": "NET", "golf_supplies": "GOLF",
    "office_supplies": "OFF", "insurance": "INS", "business_licenses": "LIC",
    "uncategorized_expense": "UNCAT_EXP", "uncategorized_income": "UNCAT_INC",
}

SAMPLE = '''2026-02-25,"SHIDDY'S DISTILLING EDMONTON, AB",411.48,,5268********8733
2026-02-25,"COSTCO BUSINESS CENTER EDMONTON, AB",282.40,,5268********9994
2026-02-17,"Spotify P3F5CB918C Stockholm, SWE",13.32,,5268********2785
2026-02-11,PRE-AUTHORIZED PAYMENT - THANK YOU,,6776.26,5268********8733
2026-01-30,"TEMU.COM VICTORIA, BC",,30.72,5268********8733
2026-02-04,"TELUS PRE-AUTH PAYMENT EDMONTON, AB",89.25,,5268********2785
'''


def _write(tmp_path):
    p = tmp_path / "cibc.csv"
    p.write_text(SAMPLE, encoding="utf-8")
    return str(p)


def _proc():
    return CreditCardProcessor(accounts=ACCT)


def test_parse_classifies_rows(tmp_path):
    rows = parse_statement(_write(tmp_path))
    kinds = {(r["merchant"][:6]): r["kind"] for r in rows}
    assert any(r["kind"] == "charge" for r in rows)
    assert any(r["kind"] == "payment" for r in rows)   # PRE-AUTHORIZED PAYMENT
    assert any(r["kind"] == "refund" for r in rows)    # TEMU credit
    pay = next(r for r in rows if r["kind"] == "payment")
    assert pay["amount_cents"] == 677626
    telus = next(r for r in rows if "TELUS" in r["merchant"])
    assert telus["kind"] == "charge"                   # a Telus charge, NOT a card payment


def test_categorize_rules():
    p = _proc()
    assert p.categorize("COSTCO CANADA LIQUOR 1 EDMONTON, AB")[0] == "alcohol"   # LIQUOR
    assert p.categorize("SEA CHANGE BREWING")[0] == "alcohol"
    assert p.categorize("Spotify P3F5CB918C")[0] == "subscription"
    assert p.categorize("TELUS PRE-AUTH PAYMENT")[0] == "computer_internet"
    assert p.categorize("FACEBK *3P646")[0] == "advertising"
    assert p.categorize("ZOOM.COM")[0] == "telephone_wireless"
    assert p.categorize("TAOBAO")[0] == "golf_supplies"
    # ambiguous -> uncategorized
    assert p.categorize("COSTCO BUSINESS CENTER")[0] == "uncategorized_expense"
    assert p.categorize("AMZN Mktp CA*153")[0] == "uncategorized_expense"
    assert p.categorize("REAL CDN WHOLESALE #67")[0] == "uncategorized_expense"


def test_charge_payload_directions():
    p = _proc()
    row = {"date": "2026-02-25", "merchant": "SHIDDY'S DISTILLING", "amount_cents": 41148,
           "kind": "charge", "occurrence": 0, "card": "8733"}
    pl = p.build_payload(row)
    assert pl["anchor_id"] == "CARD" and pl["anchor_direction"] == "WITHDRAWAL"
    assert pl["amount"] == pytest.approx(411.48, abs=0.005)
    assert pl["lines"][0]["account_id"] == "ALC"
    assert pl["lines"][0]["direction"] == "INCREASE"
    assert pl["external_id"].startswith("CC_")


def test_refund_and_payment_payloads():
    p = _proc()
    refund = p.build_payload({"date": "2026-01-30", "merchant": "TEMU.COM", "amount_cents": 3072,
                              "kind": "refund", "occurrence": 0, "card": "8733"})
    assert refund["anchor_direction"] == "DEPOSIT"
    assert refund["lines"][0]["direction"] == "DECREASE"
    assert refund["lines"][0]["account_id"] == "UNCAT_EXP"    # Temu -> uncategorized

    pay = p.build_payload({"date": "2026-02-11", "merchant": "PRE-AUTHORIZED PAYMENT - THANK YOU",
                           "amount_cents": 677626, "kind": "payment", "occurrence": 0, "card": "8733"})
    assert pay["anchor_direction"] == "DEPOSIT"
    assert pay["lines"][0]["account_id"] == "UNCAT_INC"       # card-payment placeholder
    assert pay["lines"][0]["direction"] == "INCREASE"


def test_external_id_stable_and_disambiguates_duplicates():
    p = _proc()
    base = {"date": "2026-02-25", "merchant": "SHIDDY'S DISTILLING", "amount_cents": 41148, "kind": "charge"}
    a = p._external_id(dict(base, occurrence=0))
    a2 = p._external_id(dict(base, occurrence=0))
    b = p._external_id(dict(base, occurrence=1))
    assert a == a2       # deterministic
    assert a != b        # duplicate rows get distinct ids


def test_end_to_end_build_and_validate(tmp_path):
    rows = parse_statement(_write(tmp_path))
    payloads = _proc().build_payloads(rows)
    assert len(payloads) == len(rows)
    assert validate_payloads(payloads) == []


def test_unconfigured_account_guard_raises():
    todo_payload = {"anchor_id": "CARD",
                    "lines": [{"account_id": "TODO_UNCATEGORIZED_EXPENSE_ID", "amount": 1.0,
                               "direction": "INCREASE"}]}
    with pytest.raises(ValidationError):
        creditcard._check_accounts_configured([todo_payload])
