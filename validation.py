"""
Input & payload validation (Phase 1 / Workstream 3).

Two jobs:

  1. ``validate_summary`` — sanity-check the aggregated day *before* we build
     payloads: net-refund days, days with sales but no tenders, empty days.
     These used to be handled implicitly (or not at all).

  2. ``validate_payloads`` — structural check of every prepared Wave payload
     *before* posting any of them, so a day is posted all-or-nothing: if one
     payload is malformed we abort before touching Wave rather than leaving the
     day half-posted.

Both return plain lists so the caller decides whether to warn or abort.
"""

from logging_setup import get_logger

logger = get_logger("validation")

_MONEY_EPS = 0.005  # half a cent: below this we treat a total as zero


def validate_summary(summary):
    """
    Inspect an aggregated daily summary.

    :returns: ``(errors, warnings)`` — lists of human-readable strings.
        Errors should block auto-posting; warnings are informational.
    """
    errors, warnings = [], []
    total = float(summary.get("total_collected", 0.0))
    tenders = summary.get("tenders", {}) or {}
    tender_sum = sum(float(v) for v in tenders.values())

    if not summary.get("source_order_ids"):
        warnings.append("No completed source orders contributed to this day.")

    if total < -_MONEY_EPS:
        errors.append(
            f"Net-refund day: total_collected=${total:.2f} is negative. "
            "Auto-posting a negative anchor is unsafe — handle this day manually."
        )

    if abs(tender_sum) < _MONEY_EPS and abs(total) >= _MONEY_EPS:
        warnings.append(
            f"Sales present (total=${total:.2f}) but tenders net to $0.00 — "
            "check tender/refund mapping."
        )

    for w in warnings:
        logger.warning("Input validation: %s", w)
    for e in errors:
        logger.error("Input validation: %s", e)
    return errors, warnings


def validate_payloads(payloads):
    """
    Structurally validate prepared Wave payloads.

    :returns: a list of error strings; empty means all payloads are well-formed.
    """
    errors = []
    required = ("role", "date", "description", "amount", "lines")

    if not payloads:
        errors.append("No payloads prepared for this day.")

    for i, p in enumerate(payloads):
        label = p.get("role") or f"payload[{i}]"

        for k in required:
            if k not in p:
                errors.append(f"{label}: missing required field '{k}'")

        lines = p.get("lines") or []
        if not lines:
            errors.append(f"{label}: has no line items")

        try:
            amt = float(p.get("amount"))
            if amt < 0:
                errors.append(f"{label}: negative anchor amount {amt:.2f}")
        except (TypeError, ValueError):
            errors.append(f"{label}: non-numeric anchor amount {p.get('amount')!r}")

        for j, l in enumerate(lines):
            direction = l.get("direction")
            if direction not in ("INCREASE", "DECREASE"):
                errors.append(f"{label}: line {j} has invalid direction {direction!r}")
            if not l.get("account_id"):
                errors.append(f"{label}: line {j} missing account_id")
            try:
                la = float(l.get("amount"))
                if la < 0:
                    errors.append(f"{label}: line {j} negative amount {la:.2f}")
            except (TypeError, ValueError):
                errors.append(f"{label}: line {j} non-numeric amount {l.get('amount')!r}")

    for e in errors:
        logger.error("Payload validation: %s", e)
    return errors
