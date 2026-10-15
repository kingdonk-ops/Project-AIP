"""Data access for terms.

Repositories receive the tenant-bound connection from ``with_tenant`` and never create their own
(ADR 0002). RLS also shows ``aip_app`` the platform tenant's rows, so every tenant-level read
filters ``tenant_id`` explicitly as well.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db.session import PLATFORM_TENANT_ID

__all__ = [
    "OverrideLevel",
    "Texts",
    "active_pack_contents",
    "bound_tenant",
    "defaults",
    "overrides",
    "pack_version",
    "set_active_version",
    "tenant_default_locale",
    "upsert_override",
]

OverrideLevel = Literal["tenant", "client", "project"]
Texts = dict[str, dict[str, str]]
"""``{locale: {key: text}}``."""

_DEFAULTS = text(
    "SELECT key, default_locale, default_text FROM term_key"
    " WHERE tenant_id = :platform AND deleted_at IS NULL"
)
_DEFAULT_LOCALE = text(
    "SELECT locale FROM locale_settings"
    " WHERE tenant_id = :tenant AND project_id IS NULL AND deleted_at IS NULL"
)
# Packs merge in code order, so with two active packs the later code wins a shared key.
_ACTIVE_PACKS = text(
    "SELECT v.contents FROM term_pack p"
    " JOIN term_pack_version v ON v.id = p.active_version_id AND v.tenant_id = p.tenant_id"
    " WHERE p.tenant_id = :tenant AND p.deleted_at IS NULL"
    " ORDER BY p.code"
)
_OVERRIDES = {
    "tenant": text(
        "SELECT key, locale, text FROM term_override"
        " WHERE tenant_id = :tenant AND level = 'tenant' AND deleted_at IS NULL"
    ),
    "client": text(
        "SELECT key, locale, text FROM term_override"
        " WHERE tenant_id = :tenant AND level = 'client' AND client_org_id = :scope"
        " AND deleted_at IS NULL"
    ),
    "project": text(
        "SELECT key, locale, text FROM term_override"
        " WHERE tenant_id = :tenant AND level = 'project' AND project_id = :scope"
        " AND deleted_at IS NULL"
    ),
}
# Matches uq_term_override_scope_key_locale (expression and predicate) for ON CONFLICT.
_UPSERT_OVERRIDE = text(
    """
    INSERT INTO term_override
      (id, tenant_id, level, client_org_id, project_id, key, locale, text, created_by)
    VALUES (:id, :tenant, :level, :client, :project, :key, :locale, :text, :actor)
    ON CONFLICT (
      tenant_id, level,
      coalesce(client_org_id, project_id, '00000000-0000-0000-0000-000000000000'::uuid),
      key, locale
    ) WHERE deleted_at IS NULL
    DO UPDATE SET text = excluded.text,
                  sync_version = term_override.sync_version + 1,
                  updated_at = now()
    RETURNING id
    """
)
_PACK_VERSION = text(
    "SELECT v.pack_id, v.version, p.code FROM term_pack_version v"
    " JOIN term_pack p ON p.id = v.pack_id AND p.tenant_id = v.tenant_id"
    " WHERE v.id = :id AND v.tenant_id = :tenant AND p.deleted_at IS NULL"
)
_SET_ACTIVE = text(
    "UPDATE term_pack SET active_version_id = :version_id, updated_at = now()"
    " WHERE id = :pack AND tenant_id = :tenant AND deleted_at IS NULL"
)


_BOUND_TENANT = text("SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid")


async def bound_tenant(conn: AsyncConnection) -> UUID | None:
    """The tenant ``with_tenant`` bound this transaction to (``None`` outside one)."""
    return (await conn.execute(_BOUND_TENANT)).scalar_one()


def _add(texts: Texts, locale: str, key: str, value: str) -> None:
    texts.setdefault(locale, {})[key] = value


async def defaults(conn: AsyncConnection) -> Texts:
    """The platform default text of every catalogue key, by its default locale."""
    texts: Texts = {}
    for row in await conn.execute(_DEFAULTS, {"platform": PLATFORM_TENANT_ID}):
        _add(texts, row.default_locale, row.key, row.default_text)
    return texts


async def tenant_default_locale(conn: AsyncConnection, tenant_id: UUID) -> str | None:
    return (await conn.execute(_DEFAULT_LOCALE, {"tenant": tenant_id})).scalar_one_or_none()


async def active_pack_contents(conn: AsyncConnection, tenant_id: UUID) -> list[Mapping[str, Any]]:
    """The contents (``{key: {locale: text}}``) of the tenant's active pack versions."""
    rows = await conn.execute(_ACTIVE_PACKS, {"tenant": tenant_id})
    return [row.contents for row in rows]


async def overrides(
    conn: AsyncConnection, tenant_id: UUID, level: OverrideLevel, scope_id: UUID | None = None
) -> Texts:
    texts: Texts = {}
    rows = await conn.execute(_OVERRIDES[level], {"tenant": tenant_id, "scope": scope_id})
    for row in rows:
        _add(texts, row.locale, row.key, row.text)
    return texts


async def upsert_override(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    level: OverrideLevel,
    client_id: UUID | None,
    project_id: UUID | None,
    key: str,
    locale: str,
    text_: str,
    actor_id: UUID | None,
) -> UUID:
    params = {
        "id": uuid.uuid4(),
        "tenant": tenant_id,
        "level": level,
        "client": client_id,
        "project": project_id,
        "key": key,
        "locale": locale,
        "text": text_,
        "actor": actor_id,
    }
    return (await conn.execute(_UPSERT_OVERRIDE, params)).scalar_one()


async def pack_version(
    conn: AsyncConnection, *, tenant_id: UUID, version_id: UUID
) -> Row[Any] | None:
    """``pack_id``, ``version`` and pack ``code`` of one of the tenant's pack versions."""
    return (await conn.execute(_PACK_VERSION, {"id": version_id, "tenant": tenant_id})).first()


async def set_active_version(
    conn: AsyncConnection, *, tenant_id: UUID, pack_id: UUID, version_id: UUID
) -> bool:
    result = await conn.execute(
        _SET_ACTIVE, {"version_id": version_id, "pack": pack_id, "tenant": tenant_id}
    )
    return result.rowcount == 1
