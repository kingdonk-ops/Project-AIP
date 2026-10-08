"""Published interface of the ops module.

Other modules may import only this file. OPS-01: job records. Callers pass the tenant-bound
connection from ``with_tenant`` (ADR 0002); Procrastinate (OPS-02) carries the work itself.
"""

from __future__ import annotations

from .schemas import TERMINAL_STATUSES, JobEventView, JobStatus, JobView
from .service import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    JobNotFound,
    create_job,
    resolve_correlation_id,
    transition,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "InvalidTransition",
    "JobEventView",
    "JobNotFound",
    "JobStatus",
    "JobView",
    "create_job",
    "resolve_correlation_id",
    "transition",
    "validate_transition",
]
