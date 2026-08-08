"""
Idempotency support for posting Square daily summaries to Wave.

The daily sales journal and the cash / gift-card clearing transfers are *aggregates*
of a whole day of Square orders, so there is no single Square order id to key on.
The stable identity of each posting is therefore (payload role, location, business day):

    SQ_SALESJOURNAL_<locationId>_<YYYYMMDD>
    SQ_TRANSFER_CASH_<locationId>_<YYYYMMDD>
    SQ_TRANSFER_GIFT_CARD_<locationId>_<YYYYMMDD>

Wave's public docs do not document whether `externalId` is enforced unique server-side,
so we do NOT rely on that. Instead we keep our own append-only ledger of everything we
have successfully posted (which also serves as the Phase-1 audit trail). Re-run safety is
thus self-contained and does not depend on undocumented Wave behavior.
"""

import hashlib
import json
import os
from datetime import datetime, timezone


def deterministic_external_id(role, location_id, date_str):
    """
    Build a stable external id for a daily payload.

    :param role: one of 'sales_journal', 'transfer_cash', 'transfer_gift_card'.
    :param location_id: Square location id (may be None; falls back to 'LOC').
    :param date_str: business day 'YYYY-MM-DD'.
    """
    loc = location_id or "LOC"
    compact_date = date_str.replace("-", "")
    return f"SQ_{role.upper()}_{loc}_{compact_date}"


def content_hash(payload):
    """
    Stable hash of the financially-meaningful content of a payload, so that a
    re-run whose amounts changed (e.g. a late refund altered the day) is detected
    rather than silently skipped. Order-independent over line items.
    """
    lines = sorted(
        (
            str(l.get("account_id")),
            l.get("direction"),
            "{:.2f}".format(float(l.get("amount", 0))),
        )
        for l in payload.get("lines", [])
    )
    material = {
        "role": payload.get("role"),
        "date": payload.get("date"),
        "amount": "{:.2f}".format(float(payload.get("amount", 0))),
        "anchor_direction": payload.get("anchor_direction"),
        "anchor_id": payload.get("anchor_id"),
        "lines": lines,
    }
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class PostedLedger:
    """
    Append-only JSONL ledger of successfully posted payloads.

    Each line records: external_id, content hash, the Square-derived amount, the
    Wave transaction id returned, and a UTC timestamp — enough to (a) prevent
    double-posting on re-run and (b) trace every automated entry back to its day.
    """

    def __init__(self, path="logs/posted_ledger.jsonl"):
        self.path = path
        self._by_external_id = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                # Last write for an external_id wins (supports --replace history).
                self._by_external_id[entry.get("external_id")] = entry

    def find(self, external_id):
        """Return the most recent ledger entry for external_id, or None."""
        return self._by_external_id.get(external_id)

    def record(self, external_id, hash_value, amount, wave_transaction_id, extra=None):
        """Append a success record and update the in-memory index."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        entry = {
            "external_id": external_id,
            "content_hash": hash_value,
            "amount": "{:.2f}".format(float(amount)),
            "wave_transaction_id": wave_transaction_id,
            "posted_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            entry.update(extra)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        self._by_external_id[external_id] = entry
        return entry
