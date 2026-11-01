"""Data access for portal users and grants (PORTAL-01).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, exists, func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.portal.tables import portal_grants, portal_users

__all__ = [
    "Row",
    "get_grant",
    "get_user",
    "get_user_by_user_id",
    "grants_expiring_between",
    "insert_grant",
    "insert_user",
    "list_users",
    "lock_user",
    "renew_grant",
    "revoke_grant",
    "revoke_project_grants",
    "unrevoked_grants",
    "update_user",
]

Row = dict[str, Any]


def _live_user() -> ColumnElement[bool]:
    return portal_users.c.deleted_at.is_(None)


def _unrevoked() -> ColumnElement[bool]:
    return portal_grants.c.revoked_at.is_(None) & portal_grants.c.deleted_at.is_(None)


# --- portal users -----------------------------------------------------------------------------


async def insert_user(conn: AsyncConnection, values: dict[str, Any]) -> Row:
    stmt = insert(portal_users).values(**values).returning(*portal_users.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get_user(conn: AsyncConnection, portal_user_id: UUID) -> Row | None:
    stmt = select(portal_users).where(portal_users.c.id == portal_user_id, _live_user())
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def lock_user(conn: AsyncConnection, portal_user_id: UUID) -> Row | None:
    """The live portal user, locked for this transaction (status changes serialise)."""
    stmt = (
        select(portal_users)
        .where(portal_users.c.id == portal_user_id, _live_user())
        .with_for_update()
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def get_user_by_user_id(conn: AsyncConnection, user_id: UUID) -> Row | None:
    stmt = select(portal_users).where(portal_users.c.user_id == user_id, _live_user())
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def update_user(conn: AsyncConnection, portal_user_id: UUID, patch: dict[str, Any]) -> Row:
    stmt = (
        update(portal_users)
        .where(portal_users.c.id == portal_user_id, _live_user())
        .values(**patch, updated_at=func.now(), sync_version=portal_users.c.sync_version + 1)
        .returning(*portal_users.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


async def list_users(
    conn: AsyncConnection,
    *,
    limit: int,
    after: UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    user_ids: Iterable[UUID] = (),
    project_id: UUID | None = None,
    expiring_within: timedelta | None = None,
) -> list[Row]:
    """Up to ``limit + 1`` live portal users after ``after``, oldest first (UUIDv7 ids).

    ``q`` matches a substring of the company name (case-insensitive), or the row's ``user_id`` is
    one of ``user_ids`` (the identity users whose email matched). ``project_id`` keeps users with an
    unrevoked grant on that project; ``expiring_within`` keeps users with a live grant whose
    ``expires_at`` is in ``(now, now + expiring_within]`` (PORTAL-07).
    """
    stmt = select(portal_users).where(_live_user())
    if status is not None:
        stmt = stmt.where(portal_users.c.status == status)
    if project_id is not None:
        stmt = stmt.where(_has_grant(portal_grants.c.project_id == project_id))
    if expiring_within is not None:
        stmt = stmt.where(
            _has_grant(
                portal_grants.c.expires_at > func.now(),
                portal_grants.c.expires_at <= func.now() + expiring_within,
            )
        )
    if q:
        pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        matches: list[ColumnElement[bool]] = [
            portal_users.c.company_name.ilike(pattern, escape="\\")
        ]
        ids = list(user_ids)
        if ids:
            matches.append(portal_users.c.user_id.in_(ids))
        stmt = stmt.where(or_(*matches))
    if after is not None:
        stmt = stmt.where(portal_users.c.id > after)
    stmt = stmt.order_by(portal_users.c.id).limit(limit + 1)
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


def _has_grant(*conditions: ColumnElement[bool]) -> ColumnElement[bool]:
    """The portal user has an unrevoked grant matching ``conditions``."""
    return exists().where(
        portal_grants.c.portal_user_id == portal_users.c.id, _unrevoked(), *conditions
    )


# --- portal grants ----------------------------------------------------------------------------


async def insert_grant(conn: AsyncConnection, values: dict[str, Any]) -> Row:
    stmt = insert(portal_grants).values(**values).returning(*portal_grants.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get_grant(conn: AsyncConnection, grant_id: UUID, *, lock: bool = False) -> Row | None:
    """A grant that is not soft-deleted (revoked ones included)."""
    stmt = select(portal_grants).where(
        portal_grants.c.id == grant_id, portal_grants.c.deleted_at.is_(None)
    )
    if lock:
        stmt = stmt.with_for_update()
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def unrevoked_grants(conn: AsyncConnection, portal_user_ids: Iterable[UUID]) -> list[Row]:
    """The grants of these portal users that are not revoked (live or expired), oldest first."""
    ids = list(portal_user_ids)
    if not ids:
        return []
    stmt = (
        select(portal_grants)
        .where(portal_grants.c.portal_user_id.in_(ids), _unrevoked())
        .order_by(portal_grants.c.id)
    )
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]


async def renew_grant(
    conn: AsyncConnection, grant_id: UUID, *, access_days: int, renewed_by: UUID
) -> Row:
    stmt = (
        update(portal_grants)
        .where(portal_grants.c.id == grant_id, _unrevoked())
        .values(
            access_days=access_days,
            expires_at=func.now() + func.make_interval(0, 0, 0, access_days),
            renewed_at=func.now(),
            renewed_by=renewed_by,
            updated_at=func.now(),
        )
        .returning(*portal_grants.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


async def revoke_grant(
    conn: AsyncConnection, grant_id: UUID, *, reason: str, revoked_by: UUID | None
) -> Row | None:
    """Revoke one unrevoked grant; ``None`` when it is absent or already revoked."""
    stmt = (
        update(portal_grants)
        .where(portal_grants.c.id == grant_id, _unrevoked())
        .values(
            revoked_at=func.now(),
            revoked_by=revoked_by,
            revoked_reason=reason,
            updated_at=func.now(),
        )
        .returning(*portal_grants.c)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def revoke_project_grants(
    conn: AsyncConnection, project_id: UUID, *, reason: str, revoked_by: UUID | None
) -> list[Row]:
    """Revoke every unrevoked grant on ``project_id``; returns them (none on a second call)."""
    stmt = (
        update(portal_grants)
        .where(portal_grants.c.project_id == project_id, _unrevoked())
        .values(
            revoked_at=func.now(),
            revoked_by=revoked_by,
            revoked_reason=reason,
            updated_at=func.now(),
        )
        .returning(*portal_grants.c)
    )
    rows = [dict(r) for r in (await conn.execute(stmt)).mappings()]
    return sorted(rows, key=lambda r: r["id"])


async def grants_expiring_between(
    conn: AsyncConnection, start: datetime, end: datetime
) -> list[Row]:
    """Unrevoked grants whose ``expires_at`` is in ``[start, end)``, soonest first (PORTAL-08)."""
    stmt = (
        select(portal_grants)
        .where(_unrevoked(), portal_grants.c.expires_at >= start, portal_grants.c.expires_at < end)
        .order_by(portal_grants.c.expires_at, portal_grants.c.id)
    )
    return [dict(r) for r in (await conn.execute(stmt)).mappings()]
