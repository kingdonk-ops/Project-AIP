"""Per-tenant release flags: the code registry and ``FlagService`` (ARCH-08, ADR 0008).

A release flag is a rollout switch or kill switch for a deferred module (BIM, AI). It is not an
entitlement: what a tenant paid for is ``EntitlementService`` (ENT-01), and a gated route needs
both (see ``requires_flag``).

Known flags and their defaults live here in code; a tenant's ``tenant_feature_flags`` row overrides
the default, and a missing row means the default. An unknown flag name raises ``UnknownFlagError``
everywhere, before any SQL, so a typo cannot silently read as "off".

``FlagService.set`` writes the tenant's value and, when the effective value changes, emits
``platform.flag.changed {flag, enabled}`` through ``emit`` on the same connection, so the event
commits or rolls back with the change. It needs a request context (``emit`` takes the tenant and
actor from it).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.context import get_context, new_request_id
from aip.platform.events.outbox import Aggregate, emit
from aip.platform.events.registry import PLATFORM_FLAG_CHANGED

__all__ = [
    "FLAG_CHANGED",
    "FlagChange",
    "FlagService",
    "UnknownFlagError",
    "check_flag",
    "known_flags",
    "register_flag",
]

FLAG_CHANGED: Final = PLATFORM_FLAG_CHANGED

# The deferred modules' flags (arch module README: "Per-tenant feature flags for deferred modules
# (BIM, AI)"). Off until a tenant is rolled out.
_DEFAULTS: dict[str, bool] = {"ai": False, "bim": False}


class UnknownFlagError(KeyError):
    """The flag is not in the code registry."""

    def __init__(self, flag: str) -> None:
        self.flag = flag
        super().__init__(f"unknown feature flag: {flag!r}")


def register_flag(flag: str, default: bool) -> None:
    """Add a flag to the registry (idempotent for the same default)."""
    current = _DEFAULTS.get(flag)
    if current is not None and current != default:
        raise ValueError(f"feature flag {flag!r} is already registered with default {current}")
    _DEFAULTS[flag] = default


def known_flags() -> Mapping[str, bool]:
    """Every known flag and its default, read-only."""
    return MappingProxyType(_DEFAULTS)


def check_flag(flag: str) -> bool:
    """The flag's default; raises ``UnknownFlagError`` when it is not registered."""
    try:
        return _DEFAULTS[flag]
    except KeyError:
        raise UnknownFlagError(flag) from None


@dataclass(frozen=True, slots=True)
class FlagChange:
    flag: str
    enabled: bool
    changed: bool


_SELECT_ONE = text(
    "SELECT enabled FROM tenant_feature_flags WHERE flag = :flag AND deleted_at IS NULL"
)
_SELECT_ALL = text("SELECT flag, enabled FROM tenant_feature_flags WHERE deleted_at IS NULL")
# ``set`` first makes sure a live row exists (holding the default), then locks it, so concurrent
# changes of one flag serialise and each compares against the value the previous one committed.
_ENSURE_ROW = text("""
INSERT INTO tenant_feature_flags (id, tenant_id, flag, enabled, updated_by)
VALUES (:id, NULLIF(current_setting('app.tenant_id', true), '')::uuid, :flag, :default, NULL)
ON CONFLICT (tenant_id, flag) WHERE deleted_at IS NULL DO NOTHING
""")
_LOCK_ROW = text("""
SELECT id, enabled FROM tenant_feature_flags
WHERE flag = :flag AND deleted_at IS NULL FOR UPDATE
""")
_UPDATE = text("""
UPDATE tenant_feature_flags SET enabled = :enabled, updated_by = :by, updated_at = now()
WHERE id = :id
""")


class FlagService:
    """Stateless; every method runs on the caller's ``with_tenant`` connection."""

    async def is_enabled(self, conn: AsyncConnection, flag: str) -> bool:
        default = check_flag(flag)
        stored: bool | None = (await conn.execute(_SELECT_ONE, {"flag": flag})).scalar_one_or_none()
        return default if stored is None else stored

    async def all(self, conn: AsyncConnection) -> dict[str, bool]:
        """Every known flag's effective value for the tenant, sorted by name."""
        stored = {row.flag: row.enabled for row in await conn.execute(_SELECT_ALL)}
        return {flag: stored.get(flag, default) for flag, default in sorted(_DEFAULTS.items())}

    async def set(self, conn: AsyncConnection, flag: str, enabled: bool) -> FlagChange:
        """Store ``enabled`` for the tenant; emit ``platform.flag.changed`` if it changed."""
        default = check_flag(flag)
        ctx = get_context()
        await conn.execute(
            _ENSURE_ROW, {"id": UUID(new_request_id()), "flag": flag, "default": default}
        )
        row = (await conn.execute(_LOCK_ROW, {"flag": flag})).one()
        row_id: UUID = row.id
        before: bool = row.enabled
        if before != enabled:
            await conn.execute(_UPDATE, {"id": row_id, "enabled": enabled, "by": ctx.actor_id})
        changed = before != enabled
        if changed:
            await emit(
                conn,
                FLAG_CHANGED,
                1,
                Aggregate("tenant_feature_flag", row_id),
                {"flag": flag, "enabled": enabled},
            )
        return FlagChange(flag=flag, enabled=enabled, changed=changed)
