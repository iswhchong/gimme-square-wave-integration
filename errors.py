"""
Typed errors for the Square -> Wave pipeline (Phase 1 / Workstream 3).

Raising these instead of printing-and-continuing lets the entrypoint fail loudly
and abort *before* posting anything, which is the safe behavior for code that
touches live books.
"""


class PipelineError(Exception):
    """Base class for all pipeline errors."""


class ReconciliationError(PipelineError):
    """
    Raised when a day's computed double-entry does not balance within tolerance.

    Previously the code silently edited the largest sales line by whatever the
    discrepancy was ("Adjusting largest sales item"). A sub-cent rounding gap is
    fine to absorb; a larger gap means something is actually wrong, and quietly
    moving dollars between accounts would corrupt the books. We raise instead.
    """


class ValidationError(PipelineError):
    """Raised when a day fails pre-post validation and must not be posted."""


class HttpError(PipelineError):
    """Raised when an HTTP call fails after exhausting retries (non-transient)."""
