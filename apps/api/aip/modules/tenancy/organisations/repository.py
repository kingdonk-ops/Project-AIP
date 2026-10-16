"""Data access for organisations (TENANCY-03).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.tenancy.tables import organisations
from aip.platform.db.concurrency import update_with_version

__all__ = ["get", "insert_one", "list_live", "update"]

Row = dict[str, Any]


async def insert_one(conn: AsyncConnection, values: Mapping[str, Any]) -> Row:
    stmt = insert(organisations).values(**values).returning(*organisations.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = select(organisations).where(
        organisations.c.id == id, organisations.c.deleted_at.is_(None)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_live(
    conn: AsyncConnection, *, types: Sequence[str], statuses: Sequence[str]
) -> list[Row]:
    """Live organisations, optionally of ``types`` and ``statuses``, by name ignoring case."""
    stmt = select(organisations).where(organisations.c.deleted_at.is_(None))
    if types:
        stmt = stmt.where(organisations.c.org_type.in_(types))
    if statuses:
        stmt = stmt.where(organisations.c.status.in_(statuses))
    stmt = stmt.order_by(func.lower(organisations.c.name), organisations.c.id)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def update(
    conn: AsyncConnection, id: UUID, expected_version: int, patch: dict[str, Any]
) -> Row:
    """``ConflictError`` on a stale version, ``NotFoundError`` when absent (ADR 0002 helper)."""
    return await update_with_version(conn, organisations, id, expected_version, patch)
