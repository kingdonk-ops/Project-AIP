"""``seed_default_roles``: the 11 system roles in one tenant, idempotent (ACCESS-02, ADR 0020).

Runs on the caller's ``with_tenant`` connection, inside a request context (its events need one).
TENANCY-05 provisioning calls it through ``aip.modules.access.api``; ``aip-access seed-roles``
backfills existing tenants. For each default
role it upserts the role by code and, while the role is not customised (``customised_at`` null),
syncs its permissions to the current catalogue. A customised role is left alone (fail closed): the
catalogue codes its defaults would add are reported in ``SeedReport.pending`` so an admin can
decide: only codes that joined the catalogue after the role was customised count, so a code the
admin removed on purpose is not reported again. Deprecated codes a role still holds are never
dropped (ACCESS-01 carry-forward). A non-system role that uses a system code (possible only
before the codes were reserved) is left alone and logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.events import ROLE_CHANGED
from aip.modules.access.repository import bump_access_version
from aip.modules.access.roles import repository as repo
from aip.modules.access.roles.default_roles import ROLE_CODES, default_permissions, role_name_key
from aip.platform.context import new_request_id
from aip.platform.events import Aggregate, emit

__all__ = ["SeedReport", "default_role_permissions", "seed_default_roles"]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SeedReport:
    created: list[str] = field(default_factory=list[str])
    updated: list[str] = field(default_factory=list[str])
    pending: dict[str, list[str]] = field(default_factory=dict[str, list[str]])

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated)


async def default_role_permissions(conn: AsyncConnection) -> dict[str, frozenset[str]]:
    """Each system role's default permissions over the live catalogue."""
    return default_permissions(
        (code, module) for code, module, _ in await repo.live_catalogue(conn)
    )


async def _emit(
    conn: AsyncConnection, role_id: UUID, code: str, before: set[str] | None, after: set[str]
) -> None:
    payload = {
        "roleId": role_id,
        "code": code,
        "action": "seeded",
        "before": None if before is None else sorted(before),
        "after": sorted(after),
    }
    await emit(conn, ROLE_CHANGED, 1, Aggregate("role", role_id), payload)


async def seed_default_roles(conn: AsyncConnection) -> SeedReport:
    """Upsert the system roles of the connection's tenant; safe to run any number of times."""
    await repo.lock_tenant_roles(conn)
    defaults = await default_role_permissions(conn)
    live_codes = {code for code, _, _ in await repo.live_catalogue(conn)}
    report = SeedReport()
    for code in ROLE_CODES:
        wanted = set(defaults[code])
        role = await repo.get_role_by_code(conn, code)
        if role is None:
            role_id = UUID(new_request_id())
            await repo.insert_role(
                conn,
                role_id=role_id,
                code=code,
                name=None,
                name_term_key=role_name_key(code),
                is_system=True,
            )
            await repo.set_role_permissions(conn, role_id, wanted)
            report.created.append(code)
            await _emit(conn, role_id, code, None, wanted)
            continue
        if not role["is_system"]:
            logger.warning("role %s is a custom role using a system code; not seeded", code)
            continue
        held = set(role["permissions"])
        if role["customised_at"] is not None:
            newer = await repo.codes_added_since(conn, role["customised_at"])
            if missing := sorted((wanted - held) & newer):
                report.pending[code] = missing
            continue
        # Live codes the defaults no longer give are removed; deprecated ones are kept.
        stale_live = {c for c in held - wanted if c in live_codes}
        keep = held - wanted - stale_live
        if wanted - held or stale_live:
            await repo.set_role_permissions(conn, role["id"], wanted, keep=keep)
            report.updated.append(code)
            await _emit(conn, role["id"], code, held, wanted | keep)
    if report.changed:
        await bump_access_version(conn)
    return report
