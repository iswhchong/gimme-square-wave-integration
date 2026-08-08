"""
Centralized logging setup for the Square -> Wave pipeline.

Phase 1 / Workstream 2. Before this, the pipeline only used bare ``print()``
statements, which are fine for interactive use but leave no durable record of an
automated run. Here we configure Python ``logging`` to write to BOTH the console
and a dated log file (``logs/run_YYYYMMDD_HHMMSS.log``), so that after any run
there is an on-disk trace of exactly what happened.

The append-only posted ledger (see ``idempotency.PostedLedger``) remains the
machine-readable audit trail keyed by external id; the run log is the
human-readable narrative of a single execution. Together they satisfy the
charter's "every automated entry is traceable to a Square source ID".

Usage (call once, early, from an entrypoint)::

    from logging_setup import setup_logging
    log_path = setup_logging()          # logs/run_YYYYMMDD_HHMMSS.log
    logging.getLogger("square_to_wave").info("started")

Library modules should NOT call this; they should only do
``logger = logging.getLogger("square_to_wave.<module>")`` and log. That keeps
handler configuration a decision of the entrypoint, not of imported code.
"""

import logging
import os
from datetime import datetime

# The root logger for the whole project. Every module logs under this name
# (e.g. "square_to_wave.wave_client") so a single configuration governs them all.
ROOT_LOGGER_NAME = "square_to_wave"

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(filename)s:%(lineno)d]: %(message)s"

# Sentinel attribute so repeated calls in one process don't stack handlers.
_CONFIGURED_FLAG = "_square_to_wave_configured"


def setup_logging(log_dir="logs", level=logging.INFO, run_id=None, console=True):
    """
    Configure the project logger with a console handler and a dated file handler.

    Safe to call more than once in a process: handlers are only added on the
    first call (subsequent calls just return the existing log file path), so
    tests and re-entrant callers don't get duplicated log lines.

    :param log_dir: directory for run logs; created if missing.
    :param level: logging level for both handlers.
    :param run_id: optional explicit id for the log filename; defaults to a
        timestamp ``YYYYMMDD_HHMMSS``.
    :param console: also echo to the console (stderr). Set False for quiet runs.
    :returns: absolute path to the run log file.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(level)
    # Don't hand our records up to the (possibly noisy / re-configured) root logger.
    logger.propagate = False

    if getattr(logger, _CONFIGURED_FLAG, False):
        existing = getattr(logger, "_square_to_wave_log_path", None)
        if existing:
            return existing

    os.makedirs(log_dir, exist_ok=True)
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.abspath(os.path.join(log_dir, f"run_{run_id}.log"))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
        logger.addHandler(console_handler)

    setattr(logger, _CONFIGURED_FLAG, True)
    setattr(logger, "_square_to_wave_log_path", log_path)
    logger.info("Logging initialized -> %s", log_path)
    return log_path


def get_logger(name=None):
    """
    Return a child logger under the project root logger.

    :param name: short module name, e.g. "wave_client". If None, returns the
        project root logger.
    """
    if not name:
        return logging.getLogger(ROOT_LOGGER_NAME)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
