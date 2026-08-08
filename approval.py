"""
Prepare-then-approve gate (Phase 1 / Workstream 4).

The charter wants a human approval step before anything posts to the live books,
until the pipeline is trusted. Before this, the only gate was ``--dry-run``.

The flow this module supports:

  1. PREPARE  — fetch + aggregate + validate + build payloads, then write a
     self-contained *approval artifact* (JSON) plus a human-readable
     reconciliation summary. Nothing is posted.
  2. APPROVE  — a human reviews the summary/artifact and explicitly approves it,
     which stamps ``approved=true`` (with who/when) onto the artifact.
  3. POST     — posting reads the EXACT payloads out of the approved artifact and
     posts them. It refuses unless the artifact is approved AND its integrity
     fingerprint still matches its payloads (so edited/stale figures can't slip
     through). No second Square fetch happens between review and post, so what a
     human approved is exactly what posts.

Keeping the approved payloads *in* the artifact (rather than re-deriving them at
post time) is deliberate: review and posting operate on identical bytes, which is
what makes the gate auditable.
"""

import json
import os
from datetime import datetime, timezone

from idempotency import content_hash

SCHEMA = "gimme.approval/v1"


def payloads_fingerprint(payloads):
    """
    A stable fingerprint over a list of payloads, independent of ordering.

    Built from each payload's financial content hash (see
    ``idempotency.content_hash``), so it changes if any amount, account,
    direction, date or role changes — the things a human is approving.
    """
    per = sorted(content_hash(p) for p in payloads)
    blob = json.dumps(per, separators=(",", ":"))
    return __import__("hashlib").sha256(blob.encode("utf-8")).hexdigest()


def build_artifact(date_str, summary, payloads, location_id=None):
    """Assemble the approval artifact dict (unapproved)."""
    tenders = summary.get("tenders", {}) or {}
    reconciliation = {
        "total_collected": round(float(summary.get("total_collected", 0.0)), 2),
        "tax": round(float(summary.get("tax", 0.0)), 2),
        "tips": round(float(summary.get("tips", 0.0)), 2),
        "sales_by_account": {k: round(float(v), 2)
                             for k, v in summary.get("sales_breakdown", {}).items()},
        "tenders": {k: round(float(v), 2) for k, v in tenders.items()},
        "discounts": {k: round(float(v), 2)
                      for k, v in summary.get("discounts_breakdown", {}).items()},
        "source_order_count": len(summary.get("source_order_ids", [])),
        "source_order_ids": list(summary.get("source_order_ids", [])),
    }
    return {
        "schema": SCHEMA,
        "date": date_str,
        "location_id": location_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reconciliation": reconciliation,
        "payloads": payloads,
        "payloads_fingerprint": payloads_fingerprint(payloads),
        "approved": False,
        "approved_at_utc": None,
        "approved_by": None,
    }


def default_artifact_path(date_str, base_dir="logs"):
    compact = date_str.replace("-", "")
    return os.path.join(base_dir, f"approval_{compact}.json")


def write_artifact(path, artifact):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    return path


def load_artifact(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_integrity(artifact):
    """
    Return (ok, message). ``ok`` is False if the artifact's stored fingerprint
    does not match its payloads (tampering, or manual edit after preparation).
    """
    if artifact.get("schema") != SCHEMA:
        return False, f"unrecognized artifact schema {artifact.get('schema')!r}"
    stored = artifact.get("payloads_fingerprint")
    actual = payloads_fingerprint(artifact.get("payloads", []))
    if stored != actual:
        return False, ("payloads fingerprint mismatch — the artifact's figures were "
                       "changed after it was prepared; re-prepare and re-approve")
    return True, "ok"


def approve(artifact, approver):
    """Stamp approval. Returns (ok, message, artifact)."""
    ok, msg = verify_integrity(artifact)
    if not ok:
        return False, msg, artifact
    artifact["approved"] = True
    artifact["approved_at_utc"] = datetime.now(timezone.utc).isoformat()
    artifact["approved_by"] = approver or "unknown"
    return True, "approved", artifact


def check_postable(artifact):
    """
    Return (ok, message). Posting is only allowed for an approved artifact whose
    integrity still holds.
    """
    ok, msg = verify_integrity(artifact)
    if not ok:
        return False, msg
    if not artifact.get("approved"):
        return False, "artifact is not approved — run the approve step first"
    return True, "ok"


def render_summary(artifact):
    """Human-readable reconciliation summary as a list of text lines."""
    r = artifact["reconciliation"]
    lines = []
    lines.append(f"Approval summary for {artifact['date']} (location {artifact.get('location_id')})")
    lines.append(f"  Total collected : ${r['total_collected']:.2f}")
    lines.append(f"  Tax             : ${r['tax']:.2f}")
    lines.append(f"  Tips            : ${r['tips']:.2f}")
    lines.append(f"  Source orders   : {r['source_order_count']}")
    lines.append("  Sales by account:")
    for acct, amt in r["sales_by_account"].items():
        lines.append(f"    - {acct}: ${amt:.2f}")
    lines.append("  Tenders:")
    for k, amt in r["tenders"].items():
        lines.append(f"    - {k}: ${amt:.2f}")
    if r["discounts"]:
        lines.append("  Discounts:")
        for acct, amt in r["discounts"].items():
            lines.append(f"    - {acct}: ${amt:.2f}")
    lines.append("  Wave transactions to be posted:")
    for p in artifact["payloads"]:
        lines.append(f"    * {p.get('role')}: {p.get('description')}  anchor ${float(p.get('amount', 0)):.2f}")
        for l in p.get("lines", []):
            lines.append(f"        {l['direction']} ${float(l['amount']):.2f} -> {l['account_id']}")
    status = "APPROVED" if artifact.get("approved") else "NOT approved"
    who = artifact.get("approved_by") or "-"
    lines.append(f"  Status: {status} (by {who})")
    return lines
