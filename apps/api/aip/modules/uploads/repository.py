"""Data access for upload sessions (UPLOADS-01).

Every function takes the tenant-bound connection from ``with_tenant`` and never creates its own
(ADR 0002). RLS limits every statement to the caller's tenant; reads skip soft-deleted rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.uploads.tables import scan_results, stored_files, upload_sessions

__all__ = [
    "Row",
    "count_active_for_user",
    "expire_stale",
    "find_by_client_request_id",
    "get_for_requester",
    "get_session",
    "get_stored_file",
    "insert_scan_result",
    "insert_session",
    "insert_stored_file",
    "set_released",
    "set_status",
    "touch_expiry",
]

Row = dict[str, Any]

# Sessions still expecting bytes; they count against the per-user cap and can be confirmed.
OPEN_STATUSES = ("requested", "uploading")


def _live() -> Any:
    return upload_sessions.c.deleted_at.is_(None)


async def insert_session(conn: AsyncConnection, values: Mapping[str, Any]) -> Row:
    stmt = insert(upload_sessions).values(**values).returning(*upload_sessions.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get_session(conn: AsyncConnection, session_id: UUID) -> Row | None:
    stmt = select(upload_sessions).where(upload_sessions.c.id == session_id, _live())
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def get_for_requester(
    conn: AsyncConnection, session_id: UUID, requested_by: UUID
) -> Row | None:
    """A live session owned by ``requested_by``. ``None`` (so 404) for anyone else's session."""
    stmt = select(upload_sessions).where(
        upload_sessions.c.id == session_id,
        upload_sessions.c.requested_by == requested_by,
        _live(),
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def find_by_client_request_id(
    conn: AsyncConnection, requested_by: UUID, client_request_id: UUID
) -> Row | None:
    stmt = select(upload_sessions).where(
        upload_sessions.c.requested_by == requested_by,
        upload_sessions.c.client_request_id == client_request_id,
        _live(),
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def count_active_for_user(conn: AsyncConnection, requested_by: UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(upload_sessions)
        .where(
            upload_sessions.c.requested_by == requested_by,
            upload_sessions.c.status.in_(OPEN_STATUSES),
            _live(),
        )
    )
    return int((await conn.execute(stmt)).scalar_one())


async def set_status(
    conn: AsyncConnection, session_id: UUID, status: str, *, reject_reason: str | None = None
) -> Row:
    stmt = (
        update(upload_sessions)
        .where(upload_sessions.c.id == session_id, _live())
        .values(status=status, reject_reason=reject_reason, updated_at=func.now())
        .returning(*upload_sessions.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


async def touch_expiry(conn: AsyncConnection, session_id: UUID, expires_at: datetime) -> Row:
    stmt = (
        update(upload_sessions)
        .where(upload_sessions.c.id == session_id, _live())
        .values(expires_at=expires_at, updated_at=func.now())
        .returning(*upload_sessions.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


async def set_released(conn: AsyncConnection, session_id: UUID, file_id: UUID) -> Row:
    """Mark a session ``released`` and link it to the released ``stored_files`` row."""
    stmt = (
        update(upload_sessions)
        .where(upload_sessions.c.id == session_id, _live())
        .values(status="released", file_id=file_id, reject_reason=None, updated_at=func.now())
        .returning(*upload_sessions.c)
    )
    return dict((await conn.execute(stmt)).mappings().one())


async def insert_stored_file(conn: AsyncConnection, values: Mapping[str, Any]) -> Row:
    """Insert the released, scanned file. Called only from the pipeline's ``release`` step."""
    stmt = insert(stored_files).values(**values).returning(*stored_files.c)
    return dict((await conn.execute(stmt)).mappings().one())


async def get_stored_file(conn: AsyncConnection, file_id: UUID) -> Row | None:
    """A live released file by id; ``None`` (so 404) for another tenant's (RLS) or a deleted one."""
    stmt = select(stored_files).where(
        stored_files.c.id == file_id, stored_files.c.deleted_at.is_(None)
    )
    row = (await conn.execute(stmt)).mappings().first()
    return None if row is None else dict(row)


async def insert_scan_result(conn: AsyncConnection, values: Mapping[str, Any]) -> None:
    """Append one ``scan_results`` row (append-only: ``aip_app`` has INSERT/SELECT only)."""
    await conn.execute(insert(scan_results).values(**values))


async def expire_stale(conn: AsyncConnection, now: datetime) -> int:
    """Mark ``requested`` sessions whose TTL has passed as ``expired``. Returns how many changed."""
    stmt = (
        update(upload_sessions)
        .where(
            upload_sessions.c.status == "requested",
            upload_sessions.c.expires_at <= now,
            _live(),
        )
        .values(status="expired", updated_at=func.now())
        .returning(upload_sessions.c.id)
    )
    return len((await conn.execute(stmt)).all())
