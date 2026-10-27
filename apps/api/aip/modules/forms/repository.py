"""Data access for forms (FORMS-01).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows.
Revision writes are plain ``UPDATE``s — the ``form_revisions_freeze`` trigger is the backstop that
keeps a published revision frozen; template writes go through the optimistic ``sync_version``
helper.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Table, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.forms.tables import form_revisions, form_templates
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.soft_delete import soft_delete

__all__ = [
    "current_published_revision",
    "get_revision",
    "get_revision_with_template",
    "get_template",
    "insert_revision",
    "insert_template",
    "list_templates",
    "lock_template",
    "max_revision_no",
    "open_draft",
    "revisions_for_template",
    "soft_delete_revision",
    "update_revision",
    "update_template",
]

Row = dict[str, Any]


def _live(table: Table) -> ColumnElement[bool]:
    return table.c.deleted_at.is_(None)


def _ilike(q: str) -> ColumnElement[bool]:
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(
        form_templates.c.code.ilike(pattern, escape="\\"),
        form_templates.c.name.ilike(pattern, escape="\\"),
    )


# --- templates --------------------------------------------------------------------------------


async def insert_template(conn: AsyncConnection, values: dict[str, Any]) -> Row:
    stmt = insert(form_templates).values(**values).returning(*form_templates.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get_template(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = select(form_templates).where(form_templates.c.id == id, _live(form_templates))
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def lock_template(conn: AsyncConnection, id: UUID) -> Row | None:
    """The live template, locked ``FOR UPDATE`` so a publish serialises per template."""
    stmt = (
        select(form_templates)
        .where(form_templates.c.id == id, _live(form_templates))
        .with_for_update()
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def update_template(
    conn: AsyncConnection, id: UUID, expected_version: int, patch: dict[str, Any]
) -> Row:
    """``ConflictError`` on a stale ``sync_version``, ``NotFoundError`` when absent."""
    return await update_with_version(conn, form_templates, id, expected_version, patch)


def _published_no() -> Any:
    """Per template, the ``revision_no`` of its one published revision (else NULL)."""
    return (
        select(
            form_revisions.c.template_id.label("template_id"),
            form_revisions.c.revision_no.label("current_revision_no"),
        )
        .where(form_revisions.c.status == "published")
        .subquery()
    )


async def list_templates(
    conn: AsyncConnection, *, kind: str | None, status: str | None, q: str | None, limit: int
) -> list[Row]:
    published = _published_no()
    stmt = (
        select(form_templates, published.c.current_revision_no)
        .select_from(
            form_templates.join(
                published, published.c.template_id == form_templates.c.id, isouter=True
            )
        )
        .where(_live(form_templates))
    )
    if kind is not None:
        stmt = stmt.where(form_templates.c.kind == kind)
    if status is not None:
        stmt = stmt.where(form_templates.c.status == status)
    if q:
        stmt = stmt.where(_ilike(q))
    stmt = stmt.order_by(form_templates.c.code).limit(limit)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def template_current_revision_no(conn: AsyncConnection, template_id: UUID) -> int | None:
    stmt = select(form_revisions.c.revision_no).where(
        form_revisions.c.template_id == template_id, form_revisions.c.status == "published"
    )
    return (await conn.execute(stmt)).scalar_one_or_none()


# --- revisions --------------------------------------------------------------------------------


async def insert_revision(conn: AsyncConnection, values: dict[str, Any]) -> Row:
    stmt = insert(form_revisions).values(**values).returning(*form_revisions.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get_revision(conn: AsyncConnection, id: UUID) -> Row | None:
    stmt = select(form_revisions).where(form_revisions.c.id == id, _live(form_revisions))
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def get_revision_with_template(conn: AsyncConnection, id: UUID) -> Row | None:
    """A live revision joined to its template's ``code`` and ``kind`` (for the published API)."""
    stmt = (
        select(
            form_revisions,
            form_templates.c.code.label("template_code"),
            form_templates.c.kind.label("kind"),
        )
        .select_from(
            form_revisions.join(form_templates, form_templates.c.id == form_revisions.c.template_id)
        )
        .where(form_revisions.c.id == id, _live(form_revisions))
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def current_published_revision(conn: AsyncConnection, template_id: UUID) -> Row | None:
    stmt = select(form_revisions).where(
        form_revisions.c.template_id == template_id, form_revisions.c.status == "published"
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def open_draft(conn: AsyncConnection, template_id: UUID) -> Row | None:
    stmt = select(form_revisions).where(
        form_revisions.c.template_id == template_id,
        form_revisions.c.status == "draft",
        _live(form_revisions),
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def max_revision_no(conn: AsyncConnection, template_id: UUID) -> int:
    """The highest ``revision_no`` ever used for the template (0 when none), including superseded
    and discarded rows, so numbers are never reused."""
    stmt = select(func.coalesce(func.max(form_revisions.c.revision_no), 0)).where(
        form_revisions.c.template_id == template_id
    )
    return int((await conn.execute(stmt)).scalar_one())


async def revisions_for_template(conn: AsyncConnection, template_id: UUID) -> list[Row]:
    stmt = (
        select(form_revisions)
        .where(form_revisions.c.template_id == template_id, _live(form_revisions))
        .order_by(form_revisions.c.revision_no)
    )
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def update_revision(conn: AsyncConnection, id: UUID, patch: dict[str, Any]) -> Row:
    """A plain revision ``UPDATE`` (returns the row). The freeze trigger guards non-drafts."""
    stmt = (
        update(form_revisions)
        .where(form_revisions.c.id == id, _live(form_revisions))
        .values(**patch, updated_at=func.now())
        .returning(*form_revisions.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


async def soft_delete_revision(conn: AsyncConnection, id: UUID) -> Row:
    return await soft_delete(conn, form_revisions, id)
