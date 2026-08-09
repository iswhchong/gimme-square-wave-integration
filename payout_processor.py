"""
Map a Square payout (+ its entries) to a Wave money-transaction payload
(Workstream 2), posted via the API.

Wave's API can't create the "Transfer from <bank>" split a payout needs, so the
transfer amount is posted to a SUSPENSE account (config PAYOUT_ACCOUNTS['suspense'],
default Tee Time). Kent then re-points that one line to "Transfer from Square -
Account Receivable" in Wave and fixes the actual settlement date. Everything else
posts correctly:

    Bank (Cash on Hand)                  <- net (amount_money)   [anchor DEPOSIT]
    Suspense (placeholder for transfer)  <- released             [INCREASE = credit]
    Square Transaction Fee (CC fee)      <- Σ fee_amount_money    [INCREASE = debit]
    Square - Gift Card Fee (net of GST)  <- −Σ OTHER.gross        [INCREASE = debit]
    Taxes Recoverable/Refundable (ITC)   <- −Σ TAX_ON_FEE.gross   [INCREASE = debit]

released = net + cc_fee + gift_fee_net + gift_fee_gst, so the credit (suspense)
equals the debits (bank + fees + ITC) — a balanced double entry Wave accepts
(same shape as Kent's manual entry, with the transfer line swapped for suspense).

Square reports the gift-card fee's GST as its own TAX_ON_FEE entry, so the ITC is
Square's exact figure (no 5% math). The payload is shape-compatible with the
Phase 1 posting machinery and carries a per-payout external_id (SQ_PAYOUT_<id>)
for idempotency.
"""

from datetime import datetime

import config
from errors import ReconciliationError
from logging_setup import get_logger

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

logger = get_logger("payout_processor")

_RECON_TOLERANCE_CENTS = 1
_KNOWN_ENTRY_TYPES = {"CHARGE", "REFUND", "ADJUSTMENT", "OTHER", "TAX_ON_FEE"}


class PayoutProcessor:
    def __init__(self, accounts=None):
        self.acct = accounts if accounts is not None else config.PAYOUT_ACCOUNTS

    @staticmethod
    def _cents(money):
        return int((money or {}).get("amount", 0))

    @staticmethod
    def _tz():
        if ZoneInfo is not None:
            return ZoneInfo("America/Edmonton")
        import pytz
        return pytz.timezone("America/Edmonton")

    def transfer_datetime(self, payout):
        dt = datetime.fromisoformat(payout["created_at"].replace("Z", "+00:00"))
        return dt.astimezone(self._tz())

    def build_payload(self, payout, entries):
        """
        Convert one payout(+entries) into a Wave payload, or None to skip
        (FAILED / empty). Raises ReconciliationError if the entries don't net to
        the stated payout amount.
        """
        pid = payout.get("id")
        status = payout.get("status")
        if status == "FAILED":
            logger.warning("Payout %s is FAILED — skipping (money did not move).", pid)
            return None
        if not entries:
            logger.warning("Payout %s has no entries — skipping.", pid)
            return None

        net_c = self._cents(payout.get("amount_money"))
        sum_net_c = sum(self._cents(e.get("net_amount_money")) for e in entries)
        if abs(sum_net_c - net_c) > _RECON_TOLERANCE_CENTS:
            logger.error("Payout %s does not reconcile: entries net %d != amount_money %d",
                         pid, sum_net_c, net_c)
            raise ReconciliationError(
                f"payout {pid}: entries net ${sum_net_c/100:.2f} != stated ${net_c/100:.2f}")

        cc_fee_c = sum(self._cents(e.get("fee_amount_money")) for e in entries)
        gc_fee_net_c = -sum(self._cents(e.get("gross_amount_money"))
                            for e in entries if e.get("type") == "OTHER")
        gc_fee_gst_c = -sum(self._cents(e.get("gross_amount_money"))
                            for e in entries if e.get("type") == "TAX_ON_FEE")

        for t in sorted({e.get("type") for e in entries} - _KNOWN_ENTRY_TYPES):
            logger.warning("Payout %s has unhandled entry type %r; its gross folds "
                           "into the suspense (transfer) line — review.", pid, t)

        released_c = net_c + cc_fee_c + gc_fee_net_c + gc_fee_gst_c

        dt = self.transfer_datetime(payout)
        description = f"{dt.strftime('%b')} {dt.day} - Square Transfer"
        # Post dated to the arrival/settlement date (matches Kent's manual entry);
        # he adjusts the actual date in Wave if the bank settled differently.
        date_str = payout.get("arrival_date") or dt.strftime("%Y-%m-%d")

        def d(cents):
            return round(cents / 100.0, 2)

        if net_c >= 0:
            anchor_direction, anchor_amount = "DEPOSIT", d(net_c)
        else:
            anchor_direction, anchor_amount = "WITHDRAWAL", d(-net_c)
            logger.warning("Payout %s is a NET DEBIT (%.2f) — booking as a bank "
                           "withdrawal; please review.", pid, d(net_c))

        lines = []
        # Suspense holds the "Transfer from Square - A/R" amount (Kent re-points it).
        # INCREASE on the (income) suspense account posts it as a credit, matching
        # the transfer's effect; Kent edits this single line in Wave.
        lines.append({"account_id": self.acct["suspense"], "amount": d(abs(released_c)),
                      "direction": "INCREASE" if released_c >= 0 else "DECREASE"})
        if cc_fee_c > 0:
            lines.append({"account_id": self.acct["cc_fee"], "amount": d(cc_fee_c),
                          "direction": "INCREASE"})
        if gc_fee_net_c > 0:
            lines.append({"account_id": self.acct["gift_card_fee"], "amount": d(gc_fee_net_c),
                          "direction": "INCREASE"})
        if gc_fee_gst_c > 0:
            lines.append({"account_id": self.acct["itc"], "amount": d(gc_fee_gst_c),
                          "direction": "INCREASE"})

        return {
            "role": "payout",
            "type": "payout",
            "external_id": f"SQ_PAYOUT_{pid}",
            "date": date_str,
            "description": description,
            "amount": anchor_amount,
            "anchor_id": self.acct["bank"],
            "anchor_direction": anchor_direction,
            "lines": lines,
            "source_order_ids": [pid],
            "reconciliation": {
                "payout_id": pid,
                "status": status,
                "net": d(net_c),
                "cc_fee": d(cc_fee_c),
                "gift_card_fee_net": d(gc_fee_net_c),
                "gift_card_fee_gst": d(gc_fee_gst_c),
                "suspense_transfer": d(released_c),
                "transfer_date": dt.strftime("%Y-%m-%d"),
                "arrival_date": payout.get("arrival_date"),
                "entry_count": len(entries),
            },
        }

    def build_payloads(self, payouts_with_entries):
        out = []
        for rec in payouts_with_entries:
            p = self.build_payload(rec["payout"], rec.get("entries", []))
            if p is not None:
                out.append(p)
        return out
