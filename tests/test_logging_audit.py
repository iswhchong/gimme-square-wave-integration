"""
Phase 1 / Workstream 2 tests: structured logging & audit trail.

Covers:
  - setup_logging creates a dated run log and does not stack duplicate handlers.
  - the day's Square source order ids are captured in the summary,
  - stamped onto every prepared payload, and
  - persisted into the posted ledger when a payload is posted.

All offline: fake catalog + fake Wave client, no network, no live tokens.
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config  # noqa: E402
import main  # noqa: E402
import logging_setup  # noqa: E402
from processor import Processor  # noqa: E402
from idempotency import PostedLedger, deterministic_external_id  # noqa: E402
from tests.fixtures import SYNTHETIC_CATALOG, ExplodingSquareClient, synthetic_single_day  # noqa: E402


def _processor():
    return Processor(catalog=SYNTHETIC_CATALOG, square_client=ExplodingSquareClient())


def _reset_project_logger():
    """Undo setup_logging state so each test configures a clean logger."""
    lg = logging.getLogger(logging_setup.ROOT_LOGGER_NAME)
    for h in list(lg.handlers):
        lg.removeHandler(h)
        h.close()
    for attr in (logging_setup._CONFIGURED_FLAG, "_square_to_wave_log_path"):
        if hasattr(lg, attr):
            delattr(lg, attr)


def test_setup_logging_writes_dated_file_and_is_idempotent(tmp_path):
    _reset_project_logger()
    try:
        log_dir = str(tmp_path / "logs")
        path1 = logging_setup.setup_logging(log_dir=log_dir, run_id="20260808_101010", console=False)
        assert path1.endswith("run_20260808_101010.log")
        assert os.path.exists(path1)

        lg = logging.getLogger(logging_setup.ROOT_LOGGER_NAME)
        handlers_after_first = len(lg.handlers)

        # Second call must NOT add another set of handlers (no double logging).
        path2 = logging_setup.setup_logging(log_dir=log_dir, console=False)
        assert path2 == path1
        assert len(lg.handlers) == handlers_after_first

        lg.info("hello audit")
        for h in lg.handlers:
            h.flush()
        with open(path1, encoding="utf-8") as f:
            contents = f.read()
        assert "hello audit" in contents
    finally:
        _reset_project_logger()


def test_summary_captures_source_order_ids():
    proc = _processor()
    summary = proc.aggregate_daily_orders(synthetic_single_day(), "2026-05-23")
    assert summary["source_order_ids"] == ["ORDER_1"]


def test_payloads_are_stamped_with_source_order_ids():
    proc = _processor()
    summary = proc.aggregate_daily_orders(synthetic_single_day(), "2026-05-23")
    payloads = proc.prepare_wave_transactions(summary)
    assert payloads  # at least the sales journal
    for p in payloads:
        assert p["source_order_ids"] == ["ORDER_1"]


class _FakeWave:
    def create_transaction(self, *a, **k):
        return "WAVE_TX_1"


def test_ledger_records_source_order_ids_on_post(tmp_path):
    proc = _processor()
    summary = proc.aggregate_daily_orders(synthetic_single_day(), "2026-05-23")
    journal = next(p for p in proc.prepare_wave_transactions(summary)
                   if p["role"] == "sales_journal")

    ledger = PostedLedger(str(tmp_path / "l.jsonl"))
    result = main._post_payload_idempotent(_FakeWave(), journal, ledger)
    assert result == "posted"

    ext_id = deterministic_external_id("sales_journal", config.SQUARE_LOCATION_ID, "2026-05-23")
    entry = ledger.find(ext_id)
    assert entry["source_order_ids"] == ["ORDER_1"]
    assert entry["wave_transaction_id"] == "WAVE_TX_1"
