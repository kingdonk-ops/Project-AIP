"""The job handler registry (OPS-02): the one place a job type is declared (ADR 0003).

A module registers its handlers in its ``jobs.py``::

    from aip.modules.ops import api as ops

    async def export_report(conn: AsyncConnection, job: ops.JobView) -> str | None:
        ...  # returns the job's ``result_ref``

    ops.register("reports.export", export_report, queue="default", timeout_s=120, max_attempts=3)

``register`` stores a ``JobSpec`` and declares the Procrastinate task named after the job type, so
the worker (which imports every module's ``jobs.py``) can run it and ``enqueue`` can refuse an
unknown type.

Handler contract. A handler is called with the connection of a transaction already bound to the
job's tenant (``with_tenant(job.tenant_id)`` on the ``aip_jobs`` engine), so it only ever sees that
tenant's rows. The transaction commits together with the ``succeeded`` status and rolls back if
the handler raises or times out. Handlers MUST be idempotent: a job can run again after a worker
crash or a retry, and the run it repeats may have done external work (files, HTTP calls) that a
rollback cannot undo. Use ``job.id`` or ``job.idempotency_key`` as the key for such work.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.jobs.app import QUEUES, JobRetryStrategy, app

from . import runner
from .schemas import JobView

__all__ = [
    "DuplicateJobType",
    "InvalidJobSpec",
    "JobHandler",
    "JobSpec",
    "UnknownJobType",
    "get_spec",
    "register",
    "registered_types",
    "unregister",
]

JobHandler = Callable[[AsyncConnection, JobView], Awaitable[str | None]]

DEFAULT_RETRY_BACKOFF_S = 2


class UnknownJobType(LookupError):  # noqa: N818 - name fixed by the OPS-02 spec
    """No handler is registered for this job type."""


class DuplicateJobType(ValueError):  # noqa: N818 - reads as a domain outcome
    """A different handler is already registered for this job type."""


class InvalidJobSpec(ValueError):  # noqa: N818 - reads as a domain outcome
    """The arguments of ``register`` are not usable."""


@dataclass(frozen=True, slots=True)
class JobSpec:
    """How one job type runs."""

    job_type: str
    handler: JobHandler
    queue: str
    timeout_s: float
    max_attempts: int
    max_per_tenant: int
    retry_backoff_s: int

    def retry_strategy(self) -> JobRetryStrategy:
        return JobRetryStrategy(
            max_attempts=self.max_attempts, exponential_wait=self.retry_backoff_s
        )


_specs: dict[str, JobSpec] = {}


def register(
    job_type: str,
    handler: JobHandler,
    *,
    queue: str = "default",
    timeout_s: float,
    max_attempts: int,
    max_per_tenant: int = 2,
    retry_backoff_s: int = DEFAULT_RETRY_BACKOFF_S,
) -> JobSpec:
    """Register ``handler`` for ``job_type`` and declare its Procrastinate task.

    ``max_attempts`` is the total number of tries (1 = no retry). ``max_per_tenant`` caps how many
    jobs of this type one tenant runs at once. Registering the same handler twice with the same
    settings is a no-op (a module imported twice); a different handler raises ``DuplicateJobType``.
    """
    if not job_type:
        raise InvalidJobSpec("job_type must not be empty")
    if queue not in QUEUES:
        raise InvalidJobSpec(f"unknown queue {queue!r}; expected one of {', '.join(QUEUES)}")
    if timeout_s <= 0:
        raise InvalidJobSpec("timeout_s must be positive")
    if max_attempts < 1:
        raise InvalidJobSpec("max_attempts must be at least 1")
    if max_per_tenant < 1:
        raise InvalidJobSpec("max_per_tenant must be at least 1")
    if retry_backoff_s < 0:
        raise InvalidJobSpec("retry_backoff_s must not be negative")

    spec = JobSpec(
        job_type=job_type,
        handler=handler,
        queue=queue,
        timeout_s=timeout_s,
        max_attempts=max_attempts,
        max_per_tenant=max_per_tenant,
        retry_backoff_s=retry_backoff_s,
    )
    existing = _specs.get(job_type)
    if existing is not None:
        if existing == spec:
            return existing
        raise DuplicateJobType(f"job type {job_type!r} is already registered")

    async def task(
        job_id: str,
        tenant_id: str,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        await runner.run_job(
            spec, job_id=job_id, tenant_id=tenant_id, actor_id=actor_id, request_id=request_id
        )

    app.task(name=job_type, queue=queue, retry=spec.retry_strategy())(task)
    _specs[job_type] = spec
    return spec


def get_spec(job_type: str) -> JobSpec:
    """The spec of ``job_type``; raises ``UnknownJobType``."""
    try:
        return _specs[job_type]
    except KeyError:
        raise UnknownJobType(f"no handler is registered for job type {job_type!r}") from None


def registered_types() -> frozenset[str]:
    return frozenset(_specs)


def unregister(job_type: str) -> None:
    """Forget ``job_type`` (tests only: a worker never unregisters). Unknown types are ignored."""
    if _specs.pop(job_type, None) is not None:
        app.tasks.pop(job_type, None)
