"""
HTTP helper with timeouts and bounded retry/backoff (Phase 1 / Workstream 3).

The pipeline previously issued bare ``requests.post(...)`` calls with no timeout
and no retry: a hung connection would block forever, and a transient 502 from
Square or Wave would abort the whole run. This wraps POSTs with:

  - a connect/read timeout (so a call can never hang indefinitely), and
  - bounded exponential backoff on *transient* failures only
    (connection errors, timeouts, HTTP 429 and 5xx).

Non-transient responses (e.g. HTTP 400/401/403) are returned immediately for the
caller to handle — we do not retry a request that will never succeed.

The ``sleep`` parameter is injectable so tests can exercise the retry path
without actually waiting.
"""

import time

import requests

from logging_setup import get_logger

logger = get_logger("http")

DEFAULT_TIMEOUT = 30          # seconds (connect + read)
DEFAULT_MAX_RETRIES = 3       # retries AFTER the first attempt
DEFAULT_BACKOFF_BASE = 1.0    # seconds; delay = base * 2**(attempt-1)

# Statuses worth retrying: rate-limit + transient server errors.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def post_with_retry(url, *, json=None, headers=None, timeout=DEFAULT_TIMEOUT,
                    max_retries=DEFAULT_MAX_RETRIES, backoff_base=DEFAULT_BACKOFF_BASE,
                    sleep=time.sleep, poster=None):
    """
    POST ``url`` with a timeout and bounded retry/backoff on transient failures.

    :param poster: callable with the same signature as ``requests.post``;
        defaults to ``requests.post``. Injectable for tests.
    :returns: the final ``requests.Response`` (which may still be a non-2xx the
        caller must handle).
    :raises requests.exceptions.RequestException: if every attempt raised a
        transport-level error (timeout / connection error).
    """
    do_post = poster or requests.post
    attempt = 0
    last_exc = None
    while attempt <= max_retries:
        attempt += 1
        try:
            resp = do_post(url, json=json, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt > max_retries:
                logger.error("POST %s failed after %d attempt(s): %s", url, attempt, e)
                raise
            delay = backoff_base * (2 ** (attempt - 1))
            logger.warning("POST %s transient transport error (attempt %d/%d): %s; retrying in %.1fs",
                           url, attempt, max_retries + 1, e, delay)
            sleep(delay)
            continue

        if resp.status_code in RETRYABLE_STATUS and attempt <= max_retries:
            delay = backoff_base * (2 ** (attempt - 1))
            logger.warning("POST %s -> HTTP %d (attempt %d/%d); retrying in %.1fs",
                           url, resp.status_code, attempt, max_retries + 1, delay)
            sleep(delay)
            continue

        return resp

    # Loop only exits via return or raise; this is a safety net.
    if last_exc:
        raise last_exc
    raise RuntimeError("post_with_retry exhausted attempts unexpectedly")


def get_with_retry(url, *, params=None, headers=None, timeout=DEFAULT_TIMEOUT,
                   max_retries=DEFAULT_MAX_RETRIES, backoff_base=DEFAULT_BACKOFF_BASE,
                   sleep=time.sleep, getter=None):
    """
    GET ``url`` with a timeout and bounded retry/backoff on transient failures.

    Mirror of ``post_with_retry`` for the read APIs (e.g. Square Payouts).

    :param getter: callable like ``requests.get``; defaults to ``requests.get``.
    :returns: the final ``requests.Response``.
    :raises requests.exceptions.RequestException: if every attempt raised a
        transport-level error.
    """
    do_get = getter or requests.get
    attempt = 0
    last_exc = None
    while attempt <= max_retries:
        attempt += 1
        try:
            resp = do_get(url, params=params, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt > max_retries:
                logger.error("GET %s failed after %d attempt(s): %s", url, attempt, e)
                raise
            delay = backoff_base * (2 ** (attempt - 1))
            logger.warning("GET %s transient transport error (attempt %d/%d): %s; retrying in %.1fs",
                           url, attempt, max_retries + 1, e, delay)
            sleep(delay)
            continue

        if resp.status_code in RETRYABLE_STATUS and attempt <= max_retries:
            delay = backoff_base * (2 ** (attempt - 1))
            logger.warning("GET %s -> HTTP %d (attempt %d/%d); retrying in %.1fs",
                           url, resp.status_code, attempt, max_retries + 1, delay)
            sleep(delay)
            continue

        return resp

    if last_exc:
        raise last_exc
    raise RuntimeError("get_with_retry exhausted attempts unexpectedly")
