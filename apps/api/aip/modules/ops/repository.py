"""Data access for the ops job records (OPS-01).

Every function takes the tenant-bound connection from ``with_tenant`` (ADR 0002) and never opens
its own. Tenant scoping is enforced by RLS; new rows take ``tenant_id`` from the transaction's
``app.tenant_id`` setting, so a missing tenant context fails closed (NOT NULL violation).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Row, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from .tables import job_events, jobs

# The tenant of the current transaction, exactly as the RLS policies read it.
CURRENT_TENANT = literal_column("NULLIF(current_setting('app.tenant_id', true), '')::uuid")

_JOB_COLUMNS = [c for c in jobs.c if c.name != "deleted_at"]


async def insert_job(conn: AsyncConnection, values: dict[str, Any]) -> Row[Any] | None:
    """Insert a job; ``None`` when ``(tenant, job_type, idempotency_key)`` already exists."""
    stmt = (
        insert(jobs)
        .values(**values, tenant_id=CURRENT_TENANT)
        .on_conflict_do_nothing(
            index_elements=[jobs.c.tenant_id, jobs.c.job_type, jobs.c.idempotency_key],
            index_where=jobs.c.idempotency_key.is_not(None),
        )
        .returning(*_JOB_COLUMNS)
    )
    return (await conn.execute(stmt)).one_or_none()


async def get_job_by_key(
    conn: AsyncConnection, *, job_type: str, idempotency_key: str
) -> Row[Any] | None:
    stmt = select(*_JOB_COLUMNS).where(
        jobs.c.tenant_id == CURRENT_TENANT,
        jobs.c.job_type == job_type,
        jobs.c.idempotency_key == idempotency_key,
    )
    return (await conn.execute(stmt)).one_or_none()


async def lock_job(conn: AsyncConnection, job_id: UUID) -> Row[Any] | None:
    """``SELECT ... FOR UPDATE`` the live job, serialising concurrent transitions."""
    stmt = (
        select(*_JOB_COLUMNS)
        .where(jobs.c.id == job_id, jobs.c.deleted_at.is_(None))
        .with_for_update()
    )
    return (await conn.execute(stmt)).one_or_none()


async def update_job(conn: AsyncConnection, job_id: UUID, values: dict[str, Any]) -> Row[Any]:
    stmt = (
        update(jobs)
        .where(jobs.c.id == job_id)
        .values(**values, updated_at=func.now())
        .returning(*_JOB_COLUMNS)
    )
    return (await conn.execute(stmt)).one()


async def next_event_seq(conn: AsyncConnection, job_id: UUID) -> int:
    """The next ``seq`` for ``job_id``; callers hold the job row lock, so it cannot race."""
    stmt = select(func.coalesce(func.max(job_events.c.seq), 0) + 1).where(
        job_events.c.job_id == job_id
    )
    return int((await conn.execute(stmt)).scalar_one())


async def insert_event(conn: AsyncConnection, values: dict[str, Any]) -> None:
    await conn.execute(insert(job_events).values(**values))


async def count_jobs_of_type(conn: AsyncConnection, job_type: str) -> int:
    """How many jobs of ``job_type`` the current tenant has (soft-deleted ones included)."""
    stmt = select(func.count()).select_from(jobs).where(jobs.c.job_type == job_type)
    return int((await conn.execute(stmt)).scalar_one())
