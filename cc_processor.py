"""
Turn parsed CIBC statement rows into Wave money-transaction payloads (Workstream 3).

Anchored on the CIBC Credit Card liability; each row is one Wave transaction:

  - CHARGE  : anchor WITHDRAWAL (increases what's owed); one expense line INCREASE.
              Merchant is matched against config.CC_MERCHANT_RULES; unmatched ->
              Uncategorized Expense (Kent splits it in Wave).
  - REFUND  : anchor DEPOSIT (reduces what's owed); expense line DECREASE (same
              merchant rule / Uncategorized Expense).
  - PAYMENT : anchor DEPOSIT (paying the card down); one line to Uncategorized
              Income as a placeholder that Kent re-points to "Transfer from Cash on
              Hand" (Wave's API can't create the bank->card transfer directly).

GST is posted GROSS (no per-transaction split), by decision. Each payload carries
a deterministic external_id (CC_<hash>) for idempotency, since the CSV has no
transaction id.

Payloads are shape-compatible with the Phase 1 posting machinery
(main._post_payload_idempotent / wave_client.create_transaction).
"""

import hashlib

import config
from logging_setup import get_logger

logger = get_logger("cc_processor")


class CreditCardProcessor:
    def __init__(self, accounts=None, rules=None):
        self.acct = accounts if accounts is not None else config.CC_ACCOUNTS
        self.rules = rules if rules is not None else config.CC_MERCHANT_RULES

    def categorize(self, merchant):
        """Return (account_key, matched_keyword_or_None) for a merchant string."""
        m = (merchant or "").upper()
        for keyword, acct_key in self.rules:
            if keyword.upper() in m:
                return acct_key, keyword
        return "uncategorized_expense", None

    @staticmethod
    def _external_id(row):
        material = f"{row['date']}|{row['merchant']}|{row['amount_cents']}|{row['kind']}|{row.get('occurrence', 0)}"
        return "CC_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]

    def build_payload(self, row):
        """Convert one parsed statement row into a Wave payload."""
        amount = round(row["amount_cents"] / 100.0, 2)
        if amount <= 0:
            logger.warning("Skipping non-positive row: %s", row)
            return None

        kind = row["kind"]
        merchant = row["merchant"]
        ext_id = self._external_id(row)

        if kind == "payment":
            acct_key = "uncategorized_income"
            anchor_direction = "DEPOSIT"      # paying the card down
            line_direction = "INCREASE"       # placeholder credit; re-pointed to a transfer
            role = "cc_payment"
        elif kind == "refund":
            acct_key, matched = self.categorize(merchant)
            anchor_direction = "DEPOSIT"       # money back reduces what's owed
            line_direction = "DECREASE"        # reduce the expense
            role = "cc_refund"
            if matched is None:
                logger.info("Refund '%s' unmatched -> Uncategorized Expense (review).", merchant)
        else:  # charge
            acct_key, matched = self.categorize(merchant)
            anchor_direction = "WITHDRAWAL"    # a purchase increases what's owed
            line_direction = "INCREASE"        # increase the expense
            role = "cc_charge"
            if matched is None:
                logger.info("Charge '%s' unmatched -> Uncategorized Expense (review).", merchant)

        line_account = self.acct[acct_key]

        return {
            "role": role,
            "type": role,
            "external_id": ext_id,
            "date": row["date"],
            "description": merchant,
            "amount": amount,
            "anchor_id": self.acct["card"],
            "anchor_direction": anchor_direction,
            "lines": [{"account_id": line_account, "amount": amount, "direction": line_direction}],
            "source_order_ids": [ext_id],  # audit: the statement row's stable id
            "reconciliation": {
                "kind": kind, "merchant": merchant, "amount": amount,
                "category_key": acct_key, "card_last4": row.get("card", ""),
            },
        }

    def build_payloads(self, rows):
        out = []
        for r in rows:
            p = self.build_payload(r)
            if p is not None:
                out.append(p)
        return out

    def summarize(self, payloads):
        """Human-readable per-category counts/totals for dry-run / prepare."""
        from collections import defaultdict
        agg = defaultdict(lambda: [0, 0.0])
        for p in payloads:
            k = p["reconciliation"]["category_key"]
            agg[k][0] += 1
            agg[k][1] += p["amount"]
        lines = ["--- Credit-card posting summary ---"]
        for k in sorted(agg):
            n, tot = agg[k]
            flag = "  <-- REVIEW/split in Wave" if k in ("uncategorized_expense", "uncategorized_income") else ""
            lines.append(f"  {k:22} {n:3} txn  ${tot:,.2f}{flag}")
        return lines
