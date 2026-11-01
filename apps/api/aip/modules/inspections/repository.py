"""Data access for inspections (INSPECTIONS-01) and their responses (INSPECTIONS-02).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant (and, through the ACCESS-03
project-scope policy, to projects the caller holds); reads skip soft-deleted rows.
``inspection_responses`` is append-only: there is an insert and reads, never an update or delete.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, insert, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.inspections.tables import (
    inspection_current_responses,
    inspection_responses,
    inspections,
)
from aip.platform.db.idempotency import IdempotentResult, create_idempotent

__all__ = [
    "Filters",
    "Row",
    "clock_timestamp",
    "current_responses",
    "field_history",
    "find_by_client_generated_id",
    "find_by_client_id",
    "get_inspection",
    "insert_inspection",
    "insert_response",
    "list_inspections",
    "lock_inspection",
    "set_state",
]

Row = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Filters:
    """``GET /inspections`` filters; ``project_ids`` ``None`` means every visible project."""

    asset_id: UUID | None = None
    project_id: UUID | None = None
    state: str | None = None
    kind: str | None = None
    project_ids: Collection[UUID] | None = None


def _live() -> ColumnElement[bool]:
    return inspections.c.deleted_at.is_(None)


async def insert_inspection(conn: AsyncConnection, values: dict[str, Any]) -> IdempotentResult:
    """Insert one inspection; with a ``client_generated_id`` a replay returns the first row."""
    if values.get("client_generated_id") is not None:
        return await create_idempotent(conn, inspections, values)
    stmt = insert(inspections).values(**values).returning(*inspections.c)
    return IdempotentResult(dict((await conn.execute(stmt)).mappings().one()), True)


async def find_by_client_generated_id(conn: AsyncConnection, client_id: UUID) -> Row | None:
    stmt = select(inspections).where(inspections.c.client_generated_id == client_id)
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def get_inspection(conn: AsyncConnection, inspection_id: UUID) -> Row | None:
    stmt = select(inspections).where(inspections.c.id == inspection_id, _live())
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def lock_inspection(conn: AsyncConnection, inspection_id: UUID) -> Row | None:
    """The live inspection, locked ``FOR UPDATE`` for the rest of the transaction."""
    stmt = select(inspections).where(inspections.c.id == inspection_id, _live()).with_for_update()
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_inspections(
    conn: AsyncConnection, filters: Filters, limit: int, after: tuple[datetime, UUID] | None
) -> list[Row]:
    """Up to ``limit + 1`` live rows, newest first, after ``after`` (the extra row means "more")."""
    stmt = select(inspections).where(_live())
    if filters.asset_id is not None:
        stmt = stmt.where(inspections.c.asset_id == filters.asset_id)
    if filters.project_id is not None:
        stmt = stmt.where(inspections.c.project_id == filters.project_id)
    if filters.state is not None:
        stmt = stmt.where(inspections.c.state == filters.state)
    if filters.kind is not None:
        stmt = stmt.where(inspections.c.kind == filters.kind)
    if filters.project_ids is not None:
        stmt = stmt.where(inspections.c.project_id.in_(list(filters.project_ids)))
    if after is not None:
        stmt = stmt.where(tuple_(inspections.c.created_at, inspections.c.id) < after)
    stmt = stmt.order_by(inspections.c.created_at.desc(), inspections.c.id.desc()).limit(limit + 1)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def set_state(conn: AsyncConnection, inspection_id: UUID, state: str) -> Row:
    """Cache the instance's ``current_state`` on the row (bumps ``sync_version``)."""
    stmt = (
        update(inspections)
        .where(inspections.c.id == inspection_id)
        .values(state=state, sync_version=inspections.c.sync_version + 1, updated_at=func.now())
        .returning(*inspections.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


# --- responses (INSPECTIONS-02) ----------------------------------------------------------------


async def clock_timestamp(conn: AsyncConnection) -> datetime:
    """The server clock now (not the transaction start), for ordering responses."""
    return (await conn.execute(select(func.clock_timestamp()))).scalar_one()


async def insert_response(conn: AsyncConnection, values: dict[str, Any]) -> Row:
    stmt = insert(inspection_responses).values(**values).returning(*inspection_responses.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def find_by_client_id(
    conn: AsyncConnection, inspection_id: UUID, client_id: UUID
) -> Row | None:
    t = inspection_responses
    stmt = (
        select(t)
        .where(t.c.inspection_id == inspection_id, t.c.client_id == client_id)
        .order_by(t.c.created_at, t.c.id)
        .limit(1)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def current_responses(conn: AsyncConnection, inspection_id: UUID) -> dict[str, Row]:
    """The current row per field (from the view), keyed by ``field_key``."""
    v = inspection_current_responses
    stmt = select(v).where(v.c.inspection_id == inspection_id)
    return {r["field_key"]: dict(r) for r in (await conn.execute(stmt)).mappings()}


async def field_history(conn: AsyncConnection, inspection_id: UUID, field_key: str) -> list[Row]:
    """Every row for one field, oldest first."""
    t = inspection_responses
    stmt = (
        select(t)
        .where(t.c.inspection_id == inspection_id, t.c.field_key == field_key)
        .order_by(t.c.created_at, t.c.id)
    )
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]
