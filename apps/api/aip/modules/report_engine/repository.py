"""Data access for report templates (REPORTS-01).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows. Writes
are plain ``UPDATE``s: the ``report_templates_published_immutable`` trigger is the backstop that
keeps a published row frozen.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine.tables import report_templates
from aip.platform.db.soft_delete import soft_delete

__all__ = [
    "find_version",
    "get",
    "get_published",
    "insert_template",
    "list_templates",
    "lock",
    "lock_versions",
    "soft_delete_template",
    "update_template",
]

Row = dict[str, Any]
t = report_templates


def _live() -> ColumnElement[bool]:
    return t.c.deleted_at.is_(None)


async def insert_template(conn: AsyncConnection, values: dict[str, Any]) -> Row:
    stmt = insert(t).values(**values).returning(*t.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = select(t).where(t.c.id == id, _live())
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def lock(conn: AsyncConnection, id: UUID) -> Row | None:
    """The live row, locked ``FOR UPDATE`` so concurrent publishes serialise."""
    stmt = select(t).where(t.c.id == id, _live()).with_for_update()
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def lock_versions(conn: AsyncConnection, key: str, variant: str) -> int:
    """Lock every row of ``(key, variant)`` (soft-deleted ones too, so a number is never reused)
    and return the highest ``version`` (0 when there is none)."""
    locked = select(t.c.version).where(t.c.key == key, t.c.variant == variant).with_for_update()
    versions = [int(v) for v in (await conn.execute(locked)).scalars()]
    return max(versions, default=0)


async def find_version(conn: AsyncConnection, key: str, variant: str, version: int) -> Row | None:
    """The row for ``(key, variant, version)``, soft-deleted or not (the loader's lookup)."""
    stmt = select(t).where(t.c.key == key, t.c.variant == variant, t.c.version == version)
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def get_published(conn: AsyncConnection, key: str, variant: str) -> Row | None:
    stmt = (
        select(t)
        .where(t.c.key == key, t.c.variant == variant, t.c.status == "published", _live())
        .order_by(t.c.version.desc())
        .limit(1)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_templates(
    conn: AsyncConnection,
    *,
    record_type: str | None,
    status: str | None,
    after: UUID | None,
    limit: int,
) -> list[Row]:
    """Rows in id order (UUIDv7, so creation order) after ``after``; at most ``limit``."""
    columns = [c for c in t.c if c.name not in {"body", "css", "assets", "definition"}]
    stmt = select(*columns).where(_live())
    if record_type is not None:
        stmt = stmt.where(t.c.record_type == record_type)
    if status is not None:
        stmt = stmt.where(t.c.status == status)
    if after is not None:
        stmt = stmt.where(t.c.id > after)
    stmt = stmt.order_by(t.c.id).limit(limit)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def update_template(conn: AsyncConnection, id: UUID, patch: dict[str, Any]) -> Row:
    stmt = (
        update(t)
        .where(t.c.id == id, _live())
        .values(**patch, updated_at=func.now())
        .returning(*t.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


async def soft_delete_template(conn: AsyncConnection, id: UUID) -> Row:
    return await soft_delete(conn, t, id)
