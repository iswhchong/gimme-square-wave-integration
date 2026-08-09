"""
Exit-code behavior so a fully-automated / scheduled run surfaces failures.

  - _post_status maps posting outcomes to process exit codes,
  - run_approve returns a usage code when the artifact is missing and a failure
    code when the artifact can't be approved,
  - run_post returns a usage code when the artifact is missing.

All offline: no network, no live tokens.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import approval  # noqa: E402
import main  # noqa: E402
from processor import Processor  # noqa: E402
from tests.fixtures import SYNTHETIC_CATALOG, ExplodingSquareClient, synthetic_single_day  # noqa: E402


def test_post_status_codes():
    assert main._post_status({"posted": 2}) == main.EXIT_OK
    assert main._post_status({"skipped_duplicate": 2}) == main.EXIT_OK
    assert main._post_status({}) == main.EXIT_OK
    assert main._post_status({"posted": 1, "failed": 1}) == main.EXIT_FAILURE
    assert main._post_status({"skipped_changed": 1}) == main.EXIT_FAILURE


def test_run_approve_missing_file_is_usage_error(tmp_path):
    missing = str(tmp_path / "nope.json")
    assert main.run_approve(missing, "kent") == main.EXIT_USAGE


def test_run_post_missing_file_is_usage_error(tmp_path):
    missing = str(tmp_path / "nope.json")
    assert main.run_post(missing, str(tmp_path / "l.jsonl"), None, False) == main.EXIT_USAGE


def test_run_approve_tampered_artifact_is_failure(tmp_path):
    proc = Processor(catalog=SYNTHETIC_CATALOG, square_client=ExplodingSquareClient())
    summary = proc.aggregate_daily_orders(synthetic_single_day(), "2026-05-23")
    payloads = proc.prepare_wave_transactions(summary)
    art = approval.build_artifact("2026-05-23", summary, payloads, location_id="LOC9")
    art["payloads"][0]["amount"] = 999.99  # break integrity
    path = str(tmp_path / "approval_20260523.json")
    approval.write_artifact(path, art)
    assert main.run_approve(path, "kent") == main.EXIT_FAILURE
