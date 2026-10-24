"""The job runner (OPS-02): what a Procrastinate task does for one registered job type.

One call to ``run_job`` is one try of one job, for the tenant named in the payload:

1. ``tenant_job`` puts the payload's tenant into the request context (a payload without a
   ``tenant_id`` is refused before anything runs).
2. In a first tenant transaction the ``jobs`` row is locked. A job that is already terminal
   (succeeded, failed or cancelled) is skipped, so a redelivery never runs a handler twice.
   Otherwise the attempt is counted and the job is ``running`` (committed, so it is visible).
3. The handler runs in a second tenant transaction on the ``aip_app`` engine (OPS-17, ADR 0016
   amended: handlers write tenant tables and emit events, and ``aip_jobs`` gains nothing), under
   ``asyncio.timeout(spec.timeout_s)``. If it returns, ``succeeded`` and ``result_ref`` are written
   in the same transaction, so the handler's writes and the status commit together.
   ``job.completed`` (OPS-03) is emitted in that transaction too.
4. If it raises, the transaction rolls back and a third records the outcome: ``failed`` with the
   error after the last allowed try, otherwise the job stays ``running`` with the error noted. The
   exception is re-raised so Procrastinate retries with backoff, or marks its own job failed.
   Every ``failed`` outcome emits ``job.failed`` with the status change.
5. A job cancelled while it runs (``POST /jobs/{id}/cancel``, OPS-03) is already ``cancelled``, so
   the final transition is refused: the handler's work rolls back and nothing is retried.

Memory (``WORKER_MEMORY_LIMIT_MB``): after each job the peak RSS is compared with the limit. Above
80% a warning is logged; above 95% ``on_memory_exceeded`` is called (the worker entrypoint sets it
to a graceful shutdown) so the orchestrator restarts a fresh process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import resource
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db.engine import get_engine
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.jobs import tenant_job

from . import service
from .events import JOB_COMPLETED, JOB_FAILED
from .schemas import JobStatus, JobView

if TYPE_CHECKING:
    from .registry import JobSpec

__all__ = [
    "JOB_TYPE_MISMATCH",
    "MEMORY_LIMIT_ENV",
    "MemoryGuard",
    "memory_guard",
    "run_job",
]

logger = logging.getLogger(__name__)

MEMORY_LIMIT_ENV = "WORKER_MEMORY_LIMIT_MB"
MEMORY_WARN_RATIO = 0.80
MEMORY_EXIT_RATIO = 0.95
MAX_ERROR_CHARS = 2000
JOB_TYPE_MISMATCH = "job_type_mismatch"


def _peak_rss_mb() -> float:
    """Peak RSS of this process in MB (``ru_maxrss`` is KB on Linux, bytes on macOS)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


class MemoryGuard:
    """Warns, then asks the worker to exit, as the process approaches its memory limit."""

    def __init__(
        self,
        limit_mb: float | None,
        *,
        read_rss_mb: Callable[[], float] = _peak_rss_mb,
        on_exceeded: Callable[[], None] | None = None,
    ) -> None:
        self.limit_mb = limit_mb
        self._read = read_rss_mb
        self.on_exceeded = on_exceeded

    @classmethod
    def from_env(cls) -> MemoryGuard:
        raw = os.environ.get(MEMORY_LIMIT_ENV, "").strip()
        try:
            limit = float(raw) if raw else None
        except ValueError:
            logger.warning("%s=%r is not a number; memory checks are off", MEMORY_LIMIT_ENV, raw)
            limit = None
        return cls(limit if limit and limit > 0 else None)

    def check(self) -> bool:
        """Log or act on the current usage; True when the worker was asked to exit."""
        if self.limit_mb is None:
            return False
        used = self._read()
        if used > self.limit_mb * MEMORY_EXIT_RATIO:
            logger.error(
                "worker memory %.0f MB is above %d%% of the %.0f MB limit; shutting down",
                used,
                int(MEMORY_EXIT_RATIO * 100),
                self.limit_mb,
            )
            if self.on_exceeded is not None:
                self.on_exceeded()
            return True
        if used > self.limit_mb * MEMORY_WARN_RATIO:
            logger.warning(
                "worker memory %.0f MB is above %d%% of the %.0f MB limit",
                used,
                int(MEMORY_WARN_RATIO * 100),
                self.limit_mb,
            )
        return False


# The process-wide guard; ``aip.worker`` sets ``on_exceeded``, tests may replace it.
memory_guard = MemoryGuard.from_env()


class _CancelledWhileRunning(Exception):  # noqa: N818 - internal control flow
    """The job was cancelled while its handler ran, so it cannot become ``succeeded``."""


async def _finish(
    conn: AsyncConnection,
    job_id: UUID,
    status: JobStatus,
    *,
    result_ref: str | None = None,
    error: str | None = None,
) -> JobView:
    """The final transition plus its ``job.completed``/``job.failed`` event, in one transaction."""
    job = await service.transition(conn, job_id, status, result_ref=result_ref, error=error)
    payload = {
        "jobId": job.id,
        "jobType": job.job_type,
        "status": job.status.value,
        "requestedBy": job.requested_by,
        "correlationId": job.correlation_id,
        "resultRef": job.result_ref,
        "error": job.error,
    }
    name = JOB_COMPLETED if status is JobStatus.SUCCEEDED else JOB_FAILED
    await emit(conn, name, 1, Aggregate("job", job.id), payload)
    return job


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]


@tenant_job
async def run_job(
    spec: JobSpec,
    *,
    job_id: str,
    tenant_id: str,
    actor_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Run one try of job ``job_id`` for ``tenant_id`` (see the module docstring)."""
    del actor_id, request_id  # consumed by ``tenant_job`` (they build the request context)
    jid = UUID(job_id)
    engine = get_engine()
    try:
        async with with_tenant(tenant_id, engine=engine) as conn:
            job = await service.begin_attempt(conn, jid)
        if job is None:
            logger.info("job %s is already finished; skipping redelivery", job_id)
            return
        if job.job_type != spec.job_type:
            # A queue row for task A points at a job of type B: never run A's handler on it.
            logger.error(
                "job %s is of type %s but was queued for task %s; failing it",
                job_id,
                job.job_type,
                spec.job_type,
            )
            async with with_tenant(tenant_id, engine=engine) as conn:
                await _finish(conn, jid, JobStatus.FAILED, error=JOB_TYPE_MISMATCH)
            return
        if job.attempts > spec.max_attempts:
            # Recovered after a worker died more often than the job may try.
            async with with_tenant(tenant_id, engine=engine) as conn:
                await _finish(conn, jid, JobStatus.FAILED, error="max attempts exceeded")
            return

        try:
            async with with_tenant(tenant_id, engine=engine) as conn:
                async with asyncio.timeout(spec.timeout_s):
                    result_ref = await spec.handler(conn, job)
                try:
                    await _finish(conn, jid, JobStatus.SUCCEEDED, result_ref=result_ref)
                except service.InvalidTransition as exc:
                    raise _CancelledWhileRunning from exc
        except _CancelledWhileRunning:
            logger.info("job %s was cancelled while running; its work was rolled back", job_id)
            return
        except Exception as exc:
            error = _error_text(exc)
            logger.warning(
                "job %s (%s) try %d of %d failed: %s",
                job_id,
                spec.job_type,
                job.attempts,
                spec.max_attempts,
                error,
            )
            try:
                async with with_tenant(tenant_id, engine=engine) as conn:
                    if job.attempts >= spec.max_attempts:
                        await _finish(conn, jid, JobStatus.FAILED, error=error)
                    else:
                        await service.note_retry(conn, jid, error=error)
            except service.InvalidTransition:
                # Cancelled while it ran: the cancellation stands and nothing is retried.
                logger.info("job %s was cancelled while running; not retrying", job_id)
                return
            raise
    finally:
        memory_guard.check()
