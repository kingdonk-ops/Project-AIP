"""Optimistic concurrency on ``sync_version`` (DATABASE-04).

::

    async with with_tenant(ctx) as conn:
        row = await update_with_version(conn, widgets, widget_id, 3, {"name": "new"})

One statement does the check and the write, so two writers that read the same version cannot both
win: the second waits for the first's row lock, re-evaluates ``sync_version = :expected`` against
the new row and matches nothing. It then gets ``ConflictError`` carrying the stored row.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Table, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db._sql import as_dict
from aip.platform.db.errors import ConflictError, NotFoundError

__all__ = ["update_with_version"]

# Columns a caller's patch may never set: identity, tenancy, and the helper's own bookkeeping.
PROTECTED_COLUMNS = frozenset(
    {"id", "tenant_id", "sync_version", "created_at", "updated_at", "deleted_at"}
)


async def update_with_version(
    conn: AsyncConnection,
    table: Table,
    id: UUID,
    expected_version: int,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Apply ``patch`` if the row still has ``expected_version``; return the updated row.

    Raises ``ConflictError(current=row)`` when the stored version differs and ``NotFoundError``
    when no live row has that id in the caller's tenant. ``sync_version`` is incremented and
    ``updated_at`` set by the helper; ``patch`` may not touch the protected columns.
    """
    if "sync_version" not in table.c:
        raise ValueError(f"{table.name} has no sync_version column (create it with sync=True)")
    unknown = sorted(set(patch) - set(table.c.keys()))
    protected = sorted(set(patch) & PROTECTED_COLUMNS)
    if unknown or protected:
        raise ValueError(f"cannot patch {unknown + protected}")

    stmt = (
        update(table)
        .where(
            table.c.id == id,
            table.c.sync_version == expected_version,
            table.c.deleted_at.is_(None),
        )
        .values(**patch, sync_version=table.c.sync_version + 1, updated_at=func.now())
        .returning(*table.c)
    )
    updated = (await conn.execute(stmt)).first()
    if updated is not None:
        return as_dict(updated)

    current = (await conn.execute(select(table).where(table.c.id == id))).first()
    if current is None or as_dict(current)["deleted_at"] is not None:
        raise NotFoundError(f"{table.name} {id} not found")
    raise ConflictError(as_dict(current))
