"""``enqueue``: create the job record and its Procrastinate job in the caller's transaction.

Both writes use the tenant-bound connection from ``with_tenant``, so they commit or roll back
together with the domain change that caused them: a rollback leaves no ``jobs`` row and no queue
row (ADR 0003). The payload of the queue row is only ``job_id``, ``tenant_id`` and the request
identity; the job's own payload stays in the RLS-protected ``jobs`` row.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.context import ContextMissingError, get_context
from aip.platform.jobs.app import defer_in_transaction, job_lock

from . import repository, service
from .registry import get_spec
from .schemas import JobView

__all__ = ["enqueue"]


async def enqueue(
    conn: AsyncConnection,
    job_type: str,
    payload: Mapping[str, Any],
    *,
    idempotency_key: str | None = None,
) -> JobView:
    """Create a ``queued`` job and defer it; a repeated ``idempotency_key`` returns the first job.

    Raises ``UnknownJobType`` before touching the database when no handler is registered.
    ``conn`` must come from ``with_tenant``; without a tenant the insert fails closed under RLS.
    """
    spec = get_spec(job_type)
    job = await service.create_job(
        conn, job_type=job_type, payload=payload, idempotency_key=idempotency_key
    )
    if job.procrastinate_job_id is not None:
        return job  # the same keyed request again: already queued

    # Round-robin over ``max_per_tenant`` lock slots by this tenant's job count for the type, so
    # at most that many of its jobs of this type run at once (ADR 0003 fairness).
    slot = (await repository.count_jobs_of_type(conn, job_type) - 1) % spec.max_per_tenant
    args: dict[str, Any] = {"job_id": str(job.id), "tenant_id": str(job.tenant_id)}
    if job.requested_by is not None:
        args["actor_id"] = str(job.requested_by)
    with contextlib.suppress(ContextMissingError):
        args["request_id"] = get_context().request_id
    queue_id = await defer_in_transaction(
        conn,
        task_name=job_type,
        queue=spec.queue,
        args=args,
        lock=job_lock(job.tenant_id, job_type, slot),
    )
    return await service.attach_procrastinate_job(conn, job.id, queue_id)
