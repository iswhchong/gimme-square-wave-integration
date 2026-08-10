"""
Parse a downloaded CIBC credit-card statement CSV (Workstream 3).

CIBC exports have NO header, five columns:
    date (YYYY-MM-DD), merchant, charge, payment/credit, card-last4

- a value in the charge column   -> a PURCHASE (expense)
- a value in the payment column  -> either a CARD PAYMENT (paying the card down,
  description matches config.CC_PAYMENT_KEYWORDS) or a MERCHANT REFUND.

Returns normalized dicts with an integer cents amount and a 'kind' of
'charge' | 'refund' | 'payment', plus an occurrence index so identical rows in one
file get distinct, stable ids for idempotency.
"""

import csv

import config
from logging_setup import get_logger

logger = get_logger("cibc_statement")


def _cents(text):
    text = (text or "").strip().replace(",", "").replace("$", "")
    if not text:
        return 0
    return int(round(float(text) * 100))


def _is_card_payment(merchant):
    m = (merchant or "").upper()
    return any(k in m for k in config.CC_PAYMENT_KEYWORDS)


def parse_statement(path):
    """Parse a CIBC statement CSV into normalized transaction dicts."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.reader(f):
            if not raw or len(raw) < 4:
                continue
            date = (raw[0] or "").strip()
            merchant = (raw[1] or "").strip()
            charge_c = _cents(raw[2])
            payment_c = _cents(raw[3])
            card = (raw[4].strip() if len(raw) > 4 else "")
            if not date:
                continue

            if charge_c > 0:
                kind, amount_c = "charge", charge_c
            elif payment_c > 0:
                kind = "payment" if _is_card_payment(merchant) else "refund"
                amount_c = payment_c
            else:
                logger.warning("Skipping row with no amount: %s", raw)
                continue

            rows.append({"date": date, "merchant": merchant, "amount_cents": amount_c,
                         "kind": kind, "card": card})

    # Occurrence index for identical (date, merchant, amount, kind) rows, in file
    # order — makes duplicate charges get distinct but stable ids across re-downloads.
    seen = {}
    for r in rows:
        key = (r["date"], r["merchant"], r["amount_cents"], r["kind"])
        r["occurrence"] = seen.get(key, 0)
        seen[key] = r["occurrence"] + 1

    logger.info("Parsed %d statement rows from %s (%d charges, %d refunds, %d payments).",
                len(rows), path,
                sum(1 for r in rows if r["kind"] == "charge"),
                sum(1 for r in rows if r["kind"] == "refund"),
                sum(1 for r in rows if r["kind"] == "payment"))
    return rows
