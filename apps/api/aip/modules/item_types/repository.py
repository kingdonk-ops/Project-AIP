"""Data access for item_types (ITEMTYPES-01/02).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows. Lists
are returned whole (the caps in ``policies`` keep them small), so there is no keyset paging here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Table, and_, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.item_types.tables import (
    content_types,
    item_categories,
    item_type_versions,
    item_types,
)
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.soft_delete import soft_delete

__all__ = [
    "any_published_version",
    "category_in_use",
    "content_type_in_use",
    "content_type_item_count",
    "content_type_with_count",
    "count_live",
    "count_live_categories",
    "delete_row",
    "get_category",
    "get_content_type",
    "get_item_type",
    "get_version",
    "insert_row",
    "list_categories",
    "list_content_types",
    "list_item_types",
    "list_versions",
    "live_content_type_ids",
    "live_draft",
    "lock_item_type",
    "max_live_version",
    "set_content_type_order",
    "set_published_version",
    "update_row",
]

Row = dict[str, Any]


def _live(table: Table) -> ColumnElement[bool]:
    return table.c.deleted_at.is_(None)


def _ilike(table: Table, q: str) -> ColumnElement[bool]:
    """Key or name contains ``q``, ignoring case (``%`` and ``_`` are matched literally)."""
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(table.c.key.ilike(pattern, escape="\\"), table.c.name.ilike(pattern, escape="\\"))


async def insert_row(conn: AsyncConnection, table: Table, values: Mapping[str, Any]) -> Row:
    stmt = insert(table).values(**values).returning(*table.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def update_row(
    conn: AsyncConnection, table: Table, id: UUID, expected_version: int, patch: dict[str, Any]
) -> Row:
    """``ConflictError`` on a stale version, ``NotFoundError`` when absent (ADR 0002 helper)."""
    return await update_with_version(conn, table, id, expected_version, patch)


async def delete_row(conn: AsyncConnection, table: Table, id: UUID) -> Row:
    return await soft_delete(conn, table, id)


async def count_live(conn: AsyncConnection, table: Table, *filters: ColumnElement[bool]) -> int:
    stmt = select(func.count()).select_from(table).where(_live(table), *filters)
    return int((await conn.execute(stmt)).scalar_one())


# --- content types ----------------------------------------------------------------------------


async def get_content_type(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = select(content_types).where(content_types.c.id == id, _live(content_types))
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_content_types(conn: AsyncConnection, *, show_in_nav: bool | None) -> list[Row]:
    """Live content types ordered by ``sort_order, key``, each with its live ``item_type_count``."""
    counts = (
        select(
            item_categories.c.content_type_id.label("content_type_id"),
            func.count(item_types.c.id).label("item_type_count"),
        )
        .select_from(
            item_categories.join(
                item_types,
                and_(
                    item_types.c.category_id == item_categories.c.id,
                    _live(item_types),
                ),
            )
        )
        .where(_live(item_categories))
        .group_by(item_categories.c.content_type_id)
        .subquery()
    )
    stmt = (
        select(
            content_types,
            func.coalesce(counts.c.item_type_count, 0).label("item_type_count"),
        )
        .select_from(
            content_types.join(counts, counts.c.content_type_id == content_types.c.id, isouter=True)
        )
        .where(_live(content_types))
    )
    if show_in_nav is not None:
        stmt = stmt.where(content_types.c.show_in_nav.is_(show_in_nav))
    stmt = stmt.order_by(content_types.c.sort_order, content_types.c.key)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def content_type_with_count(conn: AsyncConnection, id: UUID) -> Row | None:
    row = await get_content_type(conn, id)
    if row is None:
        return None
    return {**row, "item_type_count": await content_type_item_count(conn, id)}


async def content_type_item_count(conn: AsyncConnection, content_type_id: UUID) -> int:
    stmt = (
        select(func.count(item_types.c.id))
        .select_from(
            item_types.join(
                item_categories,
                and_(
                    item_categories.c.id == item_types.c.category_id,
                    _live(item_categories),
                ),
            )
        )
        .where(_live(item_types), item_categories.c.content_type_id == content_type_id)
    )
    return int((await conn.execute(stmt)).scalar_one())


async def content_type_in_use(conn: AsyncConnection, content_type_id: UUID) -> int:
    """How many live categories sit under this content type."""
    return await count_live(
        conn, item_categories, item_categories.c.content_type_id == content_type_id
    )


async def live_content_type_ids(conn: AsyncConnection) -> list[UUID]:
    stmt = select(content_types.c.id).where(_live(content_types))
    return list((await conn.execute(stmt)).scalars())


async def set_content_type_order(conn: AsyncConnection, ids: list[UUID]) -> None:
    """Set ``sort_order`` to 10, 20, 30... in the given order, and bump ``updated_at``."""
    for position, id in enumerate(ids, start=1):
        stmt = (
            content_types.update()
            .where(content_types.c.id == id, _live(content_types))
            .values(sort_order=position * 10, updated_at=func.now())
        )
        await conn.execute(stmt)


# --- item categories --------------------------------------------------------------------------


async def get_category(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = select(item_categories).where(item_categories.c.id == id, _live(item_categories))
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_categories(conn: AsyncConnection, content_type_id: UUID) -> list[Row]:
    stmt = (
        select(item_categories)
        .where(_live(item_categories), item_categories.c.content_type_id == content_type_id)
        .order_by(item_categories.c.sort_order, item_categories.c.key)
    )
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def count_live_categories(conn: AsyncConnection, content_type_id: UUID) -> int:
    return await content_type_in_use(conn, content_type_id)


async def category_in_use(conn: AsyncConnection, category_id: UUID) -> int:
    """How many live item types sit under this category."""
    return await count_live(conn, item_types, item_types.c.category_id == category_id)


# --- item types -------------------------------------------------------------------------------


def _item_type_select() -> Any:
    """Item types joined to their live category, carrying the resolved ``content_type_id``, the
    current published version's number and the open draft's id (ITEMTYPES-02)."""
    published = item_type_versions.alias("published")
    draft_id = (
        select(item_type_versions.c.id)
        .where(
            item_type_versions.c.item_type_id == item_types.c.id,
            item_type_versions.c.status == "draft",
            _live(item_type_versions),
        )
        .scalar_subquery()
    )
    return select(
        item_types,
        item_categories.c.content_type_id.label("content_type_id"),
        published.c.version.label("published_version"),
        draft_id.label("draft_version_id"),
    ).select_from(
        item_types.join(
            item_categories,
            and_(item_categories.c.id == item_types.c.category_id, _live(item_categories)),
        ).join(published, published.c.id == item_types.c.published_version_id, isouter=True)
    )


async def get_item_type(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = _item_type_select().where(item_types.c.id == id, _live(item_types))
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_item_types(
    conn: AsyncConnection,
    *,
    content_type_id: UUID | None,
    category_id: UUID | None,
    q: str | None,
) -> list[Row]:
    stmt = _item_type_select().where(_live(item_types))
    if content_type_id is not None:
        stmt = stmt.where(item_categories.c.content_type_id == content_type_id)
    if category_id is not None:
        stmt = stmt.where(item_types.c.category_id == category_id)
    if q:
        stmt = stmt.where(_ilike(item_types, q))
    stmt = stmt.order_by(item_types.c.key)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def lock_item_type(conn: AsyncConnection, id: UUID) -> Row | None:
    """The live item type, locked ``FOR UPDATE`` until the transaction ends."""
    stmt = select(item_types).where(item_types.c.id == id, _live(item_types)).with_for_update()
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def set_published_version(conn: AsyncConnection, id: UUID, version_id: UUID) -> None:
    stmt = (
        update(item_types)
        .where(item_types.c.id == id, _live(item_types))
        .values(published_version_id=version_id, updated_at=func.now())
    )
    await conn.execute(stmt)


async def any_published_version(conn: AsyncConnection, item_type_id: UUID) -> bool:
    stmt = select(func.count()).where(
        item_type_versions.c.item_type_id == item_type_id,
        item_type_versions.c.status == "published",
    )
    return int((await conn.execute(stmt)).scalar_one()) > 0


# --- item-type versions -----------------------------------------------------------------------


async def get_version(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = select(item_type_versions).where(
        item_type_versions.c.id == id, _live(item_type_versions)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_versions(conn: AsyncConnection, item_type_id: UUID) -> list[Row]:
    """Live versions of an item type, newest first."""
    stmt = (
        select(item_type_versions)
        .where(item_type_versions.c.item_type_id == item_type_id, _live(item_type_versions))
        .order_by(item_type_versions.c.version.desc())
    )
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def live_draft(conn: AsyncConnection, item_type_id: UUID) -> Row | None:
    stmt = select(item_type_versions).where(
        item_type_versions.c.item_type_id == item_type_id,
        item_type_versions.c.status == "draft",
        _live(item_type_versions),
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def max_live_version(conn: AsyncConnection, item_type_id: UUID) -> int:
    stmt = select(func.coalesce(func.max(item_type_versions.c.version), 0)).where(
        item_type_versions.c.item_type_id == item_type_id, _live(item_type_versions)
    )
    return int((await conn.execute(stmt)).scalar_one())
