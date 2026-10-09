"""Job record service (OPS-01): idempotent creation and the job state machine.

Procrastinate (OPS-02, ADR 0003) moves the work; this service keeps the user-visible record.

State machine: ``queued -> running -> succeeded | failed | cancelled`` and ``queued -> cancelled``.
Terminal states are final. Every state change, including the initial ``queued``, appends a
``job_events`` row whose ``seq`` counts up from 1 per job.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.context import ContextMissingError, get_context, new_request_id

from . import repository
from .schemas import JobStatus, JobView

__all__ = [
    "ALLOWED_TRANSITIONS",
    "InvalidTransition",
    "JobNotFound",
    "attach_procrastinate_job",
    "begin_attempt",
    "create_job",
    "note_retry",
    "resolve_correlation_id",
    "transition",
    "validate_transition",
]

ALLOWED_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class InvalidTransition(ValueError):  # noqa: N818 - name fixed by the OPS-01 spec
    """A job status change the state machine does not allow."""

    def __init__(self, current: JobStatus, new: JobStatus) -> None:
        super().__init__(f"job cannot move from {current.value} to {new.value}")
        self.current = current
        self.new = new


class JobNotFound(LookupError):  # noqa: N818 - reads as a domain outcome, like InvalidTransition
    """No live job with this id is visible in the current tenant."""


def _uuid7() -> UUID:
    # ``new_request_id`` is the platform's UUIDv7 generator (ARCH-04).
    return UUID(new_request_id())


def validate_transition(current: JobStatus, new: JobStatus) -> None:
    """Raise ``InvalidTransition`` unless ``current -> new`` is allowed."""
    if new not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(current, new)


def resolve_correlation_id(correlation_id: UUID | None) -> UUID:
    """The given id, else the request context's request id when it is a UUID, else a UUIDv7."""
    if correlation_id is not None:
        return correlation_id
    try:
        request_id = get_context().request_id
    except ContextMissingError:
        return _uuid7()
    try:
        return UUID(request_id)
    except ValueError:
        return _uuid7()


def _actor_id() -> UUID | None:
    try:
        return get_context().actor_id
    except ContextMissingError:
        return None


async def create_job(
    conn: AsyncConnection,
    *,
    job_type: str,
    payload: Mapping[str, Any],
    idempotency_key: str | None = None,
    correlation_id: UUID | None = None,
) -> JobView:
    """Create a queued job, or return the existing one for the same tenant, type and key.

    ``conn`` is the tenant-bound connection; the job belongs to its ``app.tenant_id``.
    ``requested_by`` is the request context's actor, if any.
    """
    if not job_type:
        raise ValueError("job_type must not be empty")
    if idempotency_key == "":
        raise ValueError("idempotency_key must be None or non-empty")
    row = await repository.insert_job(
        conn,
        {
            "id": _uuid7(),
            "job_type": job_type,
            "status": JobStatus.QUEUED.value,
            "idempotency_key": idempotency_key,
            "correlation_id": resolve_correlation_id(correlation_id),
            "payload": dict(payload),
            "requested_by": _actor_id(),
        },
    )
    if row is None:
        assert idempotency_key is not None  # only a keyed insert can conflict
        existing = await repository.get_job_by_key(
            conn, job_type=job_type, idempotency_key=idempotency_key
        )
        if existing is None:  # pragma: no cover - the conflicting row is committed and visible
            raise RuntimeError("idempotent job conflict but no visible job")
        return JobView.model_validate(existing)

    job = JobView.model_validate(row)
    await repository.insert_event(
        conn,
        {
            "id": _uuid7(),
            "tenant_id": job.tenant_id,
            "job_id": job.id,
            "seq": 1,
            "from_status": None,
            "to_status": JobStatus.QUEUED.value,
            "detail": {},
        },
    )
    return job


async def transition(
    conn: AsyncConnection,
    job_id: UUID,
    new_status: JobStatus,
    *,
    detail: Mapping[str, Any] | None = None,
    result_ref: str | None = None,
    error: str | None = None,
) -> JobView:
    """Move a job to ``new_status`` under a row lock and append the matching event.

    Entering ``running`` counts an attempt. ``result_ref`` and ``error`` are stored when given.
    Raises ``JobNotFound`` or ``InvalidTransition``.
    """
    row = await repository.lock_job(conn, job_id)
    if row is None:
        raise JobNotFound(f"job {job_id} not found")
    current = JobView.model_validate(row)
    validate_transition(current.status, new_status)

    values: dict[str, Any] = {"status": new_status.value}
    if new_status is JobStatus.RUNNING:
        values["attempts"] = current.attempts + 1
    if result_ref is not None:
        values["result_ref"] = result_ref
    if error is not None:
        values["error"] = error
    updated = JobView.model_validate(await repository.update_job(conn, job_id, values))

    await repository.insert_event(
        conn,
        {
            "id": _uuid7(),
            "tenant_id": current.tenant_id,
            "job_id": job_id,
            "seq": await repository.next_event_seq(conn, job_id),
            "from_status": current.status.value,
            "to_status": new_status.value,
            "detail": dict(detail or {}),
        },
    )
    return updated


async def attach_procrastinate_job(
    conn: AsyncConnection, job_id: UUID, procrastinate_job_id: int
) -> JobView:
    """Record which Procrastinate job carries ``job_id`` (set once, by the enqueue)."""
    row = await repository.lock_job(conn, job_id)
    if row is None:
        raise JobNotFound(f"job {job_id} not found")
    return JobView.model_validate(
        await repository.update_job(conn, job_id, {"procrastinate_job_id": procrastinate_job_id})
    )


async def begin_attempt(conn: AsyncConnection, job_id: UUID) -> JobView | None:
    """Start one run of the job; ``None`` when it is already terminal (redelivery, cancelled).

    ``queued`` moves to ``running`` (the normal transition). A job already ``running`` is being
    retried or recovered after a worker died: it stays ``running`` and only the attempt counter
    and a ``running -> running`` event (``detail.attempt``) record the new try.
    Raises ``JobNotFound``.
    """
    row = await repository.lock_job(conn, job_id)
    if row is None:
        raise JobNotFound(f"job {job_id} not found")
    current = JobView.model_validate(row)
    if current.status.is_terminal:
        return None
    if current.status is JobStatus.QUEUED:
        return await transition(conn, job_id, JobStatus.RUNNING, detail={"attempt": 1})
    attempt = current.attempts + 1
    updated = JobView.model_validate(
        await repository.update_job(conn, job_id, {"attempts": attempt})
    )
    await _append_running_event(conn, updated, {"attempt": attempt})
    return updated


async def note_retry(conn: AsyncConnection, job_id: UUID, *, error: str) -> JobView:
    """Keep the job ``running`` after a failed try that will be retried; store the error."""
    row = await repository.lock_job(conn, job_id)
    if row is None:
        raise JobNotFound(f"job {job_id} not found")
    current = JobView.model_validate(row)
    if current.status is not JobStatus.RUNNING:
        raise InvalidTransition(current.status, JobStatus.RUNNING)
    updated = JobView.model_validate(await repository.update_job(conn, job_id, {"error": error}))
    await _append_running_event(conn, updated, {"retry": True, "error": error})
    return updated


async def _append_running_event(
    conn: AsyncConnection, job: JobView, detail: Mapping[str, Any]
) -> None:
    await repository.insert_event(
        conn,
        {
            "id": _uuid7(),
            "tenant_id": job.tenant_id,
            "job_id": job.id,
            "seq": await repository.next_event_seq(conn, job.id),
            "from_status": JobStatus.RUNNING.value,
            "to_status": JobStatus.RUNNING.value,
            "detail": dict(detail),
        },
    )
