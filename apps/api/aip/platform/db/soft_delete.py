"""Soft delete helpers (DATABASE-04): ``deleted_at`` is the only delete marker.

Repositories start every read from ``active(table)`` so soft-deleted rows never leak into default
queries. Hard ``DELETE`` stays with retention jobs.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, Table, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db._sql import as_dict
from aip.platform.db.errors import NotFoundError

__all__ = ["active", "restore", "soft_delete"]


def active(table: Table) -> Select[Any]:
    """``SELECT * FROM table WHERE deleted_at IS NULL``: the default query base."""
    return select(table).where(table.c.deleted_at.is_(None))


def _bump(table: Table) -> dict[str, Any]:
    values: dict[str, Any] = {"updated_at": func.now()}
    if "sync_version" in table.c:  # sync clients must see the change
        values["sync_version"] = table.c.sync_version + 1
    return values


async def soft_delete(conn: AsyncConnection, table: Table, id: UUID) -> dict[str, Any]:
    """Mark a live row deleted and return it. ``NotFoundError`` if absent or already deleted."""
    stmt = (
        update(table)
        .where(table.c.id == id, table.c.deleted_at.is_(None))
        .values(deleted_at=func.now(), **_bump(table))
        .returning(*table.c)
    )
    row = (await conn.execute(stmt)).first()
    if row is None:
        raise NotFoundError(f"{table.name} {id} not found")
    return as_dict(row)


async def restore(conn: AsyncConnection, table: Table, id: UUID) -> dict[str, Any]:
    """Clear ``deleted_at`` on a soft-deleted row; ``NotFoundError`` if it is not deleted."""
    stmt = (
        update(table)
        .where(table.c.id == id, table.c.deleted_at.is_not(None))
        .values(deleted_at=None, **_bump(table))
        .returning(*table.c)
    )
    row = (await conn.execute(stmt)).first()
    if row is None:
        raise NotFoundError(f"{table.name} {id} is not deleted")
    return as_dict(row)
