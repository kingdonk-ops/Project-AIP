"""Data access for access (ACCESS-01).

- ``sync_permissions``: the startup catalogue sync through ``access_sync_permissions`` (the only
  write path to ``permission``), on a ``before_tenant`` connection.
- ``list_permissions``: the catalogue rows, deprecated ones included.
- ``get_access_version`` / ``bump_access_version``: the tenant's access version (ADR 0020). They
  take the connection from ``with_tenant``; the row belongs to the tenant bound to it (RLS).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "PermissionRow",
    "bump_access_version",
    "get_access_version",
    "list_permissions",
    "sync_permissions",
]

_SYNC = text("SELECT access_sync_permissions(CAST(:catalogue AS jsonb))")
_LIST = text(
    "SELECT code, module_id, description, is_privileged, deprecated_at "
    "FROM permission ORDER BY code"
)
_GET_VERSION = text("SELECT access_version FROM access_settings WHERE deleted_at IS NULL")
# A tenant without a row is at version 1, so the first bump writes 2.
_BUMP_VERSION = text(
    """
    INSERT INTO access_settings (id, tenant_id, access_version)
    VALUES (gen_random_uuid(), NULLIF(current_setting('app.tenant_id', true), '')::uuid, 2)
    ON CONFLICT (tenant_id) WHERE deleted_at IS NULL
    DO UPDATE SET access_version = access_settings.access_version + 1, updated_at = now()
    RETURNING access_version
    """
)


@dataclass(frozen=True, slots=True)
class PermissionRow:
    code: str
    module_id: str
    description: str
    is_privileged: bool
    deprecated_at: datetime | None


async def sync_permissions(conn: AsyncConnection, catalogue: list[dict[str, object]]) -> None:
    await conn.execute(_SYNC, {"catalogue": json.dumps(catalogue)})


async def list_permissions(conn: AsyncConnection) -> list[PermissionRow]:
    rows = (await conn.execute(_LIST)).all()
    return [PermissionRow(*row) for row in rows]


async def get_access_version(conn: AsyncConnection) -> int:
    value = (await conn.execute(_GET_VERSION)).scalar_one_or_none()
    return 1 if value is None else int(value)


async def bump_access_version(conn: AsyncConnection) -> int:
    """Increment the bound tenant's access version in the caller's transaction; returns it."""
    return int((await conn.execute(_BUMP_VERSION)).scalar_one())
