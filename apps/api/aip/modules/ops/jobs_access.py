"""Who may act on a job (OPS-03): pure rules, no I/O.

A job is visible to, and may be cancelled or retried by, the user who requested it or a holder of
``ops.jobs.admin`` in the tenant. Jobs of other tenants never reach these rules: RLS hides them.
"""

from __future__ import annotations

from uuid import UUID

__all__ = ["JOBS_ADMIN", "can_act_on"]

JOBS_ADMIN = "ops.jobs.admin"


def can_act_on(*, actor_id: UUID | None, requested_by: UUID | None, is_admin: bool) -> bool:
    """True for the job's requester or a jobs admin; a job with no requester is admin-only."""
    if is_admin:
        return True
    return actor_id is not None and requested_by is not None and actor_id == requested_by
