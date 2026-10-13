"""Data access for projects and sites (PROJECTS-01).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Table, and_, func, insert, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.projects.tables import projects, sites
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.soft_delete import soft_delete

__all__ = [
    "Page",
    "delete_site",
    "get_project",
    "get_site",
    "insert_project",
    "insert_site",
    "list_page",
    "list_project_ids",
    "lock_live_site",
    "search",
    "site_in_use",
    "update_project",
    "update_site",
]

Row = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Page:
    """A keyset page request: sort column and direction, and the position to start after."""

    sort: str
    descending: bool
    limit: int
    after: tuple[Any, UUID] | None = None


def _live(table: Table) -> ColumnElement[bool]:
    return table.c.deleted_at.is_(None)


async def _insert(conn: AsyncConnection, table: Table, values: Mapping[str, Any]) -> Row:
    row = (await conn.execute(insert(table).values(**values).returning(*table.c))).mappings().one()
    return dict(row)


async def _get(conn: AsyncConnection, table: Table, id: UUID) -> Row | None:
    stmt = select(table).where(table.c.id == id, _live(table))
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def list_page(
    conn: AsyncConnection, table: Table, page: Page, *filters: ColumnElement[bool]
) -> list[Row]:
    """Up to ``page.limit + 1`` live rows after ``page.after`` (the extra row means "more")."""
    key = table.c[page.sort]
    position = tuple_(key, table.c.id)
    stmt = select(table).where(_live(table), *filters)
    if page.after is not None:
        stmt = stmt.where(position < page.after if page.descending else position > page.after)
    order = (key.desc(), table.c.id.desc()) if page.descending else (key.asc(), table.c.id.asc())
    stmt = stmt.order_by(*order).limit(page.limit + 1)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


def search(table: Table, q: str) -> ColumnElement[bool]:
    """Code or name contains ``q``, ignoring case (``%`` and ``_`` are matched literally)."""
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(table.c.code.ilike(pattern, escape="\\"), table.c.name.ilike(pattern, escape="\\"))


# --- projects ---------------------------------------------------------------------------------


async def insert_project(conn: AsyncConnection, values: Mapping[str, Any]) -> Row:
    return await _insert(conn, projects, values)


async def get_project(conn: AsyncConnection, id: UUID) -> Row | None:
    return await _get(conn, projects, id)


async def update_project(
    conn: AsyncConnection, id: UUID, expected_version: int, patch: dict[str, Any]
) -> Row:
    """``ConflictError`` on a stale version, ``NotFoundError`` when absent (ADR 0002 helper)."""
    return await update_with_version(conn, projects, id, expected_version, patch)


async def list_project_ids(conn: AsyncConnection) -> list[UUID]:
    stmt = select(projects.c.id).where(_live(projects)).order_by(projects.c.id)
    return list((await conn.execute(stmt)).scalars())


# --- sites ------------------------------------------------------------------------------------


async def insert_site(conn: AsyncConnection, values: Mapping[str, Any]) -> Row:
    return await _insert(conn, sites, values)


async def get_site(conn: AsyncConnection, id: UUID) -> Row | None:
    return await _get(conn, sites, id)


async def update_site(conn: AsyncConnection, id: UUID, patch: Mapping[str, Any]) -> Row | None:
    stmt = (
        update(sites)
        .where(sites.c.id == id, _live(sites))
        .values(**patch, updated_at=func.now())
        .returning(*sites.c)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def lock_live_site(conn: AsyncConnection, site_id: UUID, *, exclusive: bool) -> bool:
    """Lock a live site row for this transaction; ``False`` if there is none.

    A project that references a site takes the shared key lock (``exclusive=False``); deleting a
    site takes the exclusive one. So a delete and a new reference to the same site serialise, and
    "in use" stays true for as long as the delete's transaction runs.
    """
    stmt = select(sites.c.id).where(sites.c.id == site_id, _live(sites))
    stmt = stmt.with_for_update() if exclusive else stmt.with_for_update(key_share=True)
    return (await conn.execute(stmt)).first() is not None


async def site_in_use(conn: AsyncConnection, site_id: UUID) -> bool:
    """Whether a live project references the site."""
    stmt = select(
        select(projects.c.id).where(and_(projects.c.site_id == site_id, _live(projects))).exists()
    )
    return bool((await conn.execute(stmt)).scalar_one())


async def delete_site(conn: AsyncConnection, site_id: UUID) -> Row:
    """Soft-delete a live site; ``NotFoundError`` when absent."""
    return await soft_delete(conn, sites, site_id)
