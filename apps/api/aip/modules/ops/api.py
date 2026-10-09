"""Published interface of the ops module.

Other modules may import only this file. OPS-01: job records. Callers pass the tenant-bound
connection from ``with_tenant`` (ADR 0002). OPS-02: ``register`` declares a job type and its
handler in the one registry (handlers must be idempotent and run inside their tenant), and
``enqueue`` creates the job and defers it to Procrastinate in the caller's transaction.
"""

from __future__ import annotations

from .enqueue import enqueue
from .registry import (
    DuplicateJobType,
    InvalidJobSpec,
    JobHandler,
    JobSpec,
    UnknownJobType,
    get_spec,
    register,
    registered_types,
)
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
    "DuplicateJobType",
    "InvalidJobSpec",
    "InvalidTransition",
    "JobEventView",
    "JobHandler",
    "JobNotFound",
    "JobSpec",
    "JobStatus",
    "JobView",
    "UnknownJobType",
    "create_job",
    "enqueue",
    "get_spec",
    "register",
    "registered_types",
    "resolve_correlation_id",
    "transition",
    "validate_transition",
]
