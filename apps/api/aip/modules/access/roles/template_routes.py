"""Operator API for the default role template (ACCESS-09, ADR 0042).

Platform operators only (``platform.roles.manage``, privileged). The ops module declares the code
(it owns the ``platform`` namespace, ADR 0029), so ``aip.main`` mounts this router (through
``aip.modules.access.api``) only when that code is in the catalogue, like the event catalogue:

- ``GET /api/v1/platform/default-roles``: every cell (module x system role) with its level, the
  level the code ships (``MATRIX``) and who last moved it;
- ``PATCH /api/v1/platform/default-roles``: move cells, all or none, with a ``reason``; setting a
  cell to its shipped level resets it. Returns the history rows written;
- ``GET /api/v1/platform/default-roles/history``: the append-only change history, newest first;
- ``POST /api/v1/platform/default-roles/sync``: run ``seed_default_roles`` in each named active
  tenant (all active tenants when ``tenantIds`` is omitted). Uncustomised system roles take the
  template; customised roles are reported (``pending`` / ``excess``), never changed (ADR 0020).

The operator's own tenant must be active. A sync re-binds the request context to each target
tenant for its own transaction (the actor stays the operator), as ENT-01's operator API does.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from aip.modules.access.roles.default_roles import LEVELS, ROLE_CODES, Level
from aip.modules.access.roles.seed import seed_default_roles
from aip.modules.access.roles.templates import LevelChange, apply_changes, list_cells, list_history
from aip.modules.ops.api import active_tenant_ids
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, requires
from aip.platform.context import get_context, use_context
from aip.platform.db.session import with_tenant
from aip.platform.http import DomainError

__all__ = ["ROLES_MANAGE_PERMISSION", "router"]

ROLES_MANAGE_PERMISSION = "platform.roles.manage"

ROLES_MANAGE = Depends(requires(ROLES_MANAGE_PERMISSION))
Operator = Annotated[AccessPrincipal, ROLES_MANAGE]

_ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"description": "Unknown role, module, level or tenant, or a guardrail refused it."},
}


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class TemplateCellOut(_Model):
    module: str
    role: str
    level: Level
    shipped_level: Level
    overridden: bool
    updated_by: UUID | None
    updated_at: datetime | None


class DefaultRoleTemplate(_Model):
    roles: list[str]
    levels: list[Level]
    cells: list[TemplateCellOut]


class CellChange(_Model):
    module: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    level: Level


class TemplatePatch(_Model):
    changes: list[CellChange] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class TemplateChangeOut(_Model):
    id: UUID
    module: str
    role: str
    level_before: Level
    level_after: Level
    changed_by: UUID | None
    reason: str
    changed_at: datetime


class TemplateChangeList(_Model):
    items: list[TemplateChangeOut]


class SyncRequest(_Model):
    tenant_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=1000)


class TenantSyncOut(_Model):
    tenant_id: UUID
    created: list[str]
    updated: list[str]
    pending: dict[str, list[str]]
    excess: dict[str, list[str]]


class SyncResult(_Model):
    tenants: list[TenantSyncOut]


def _change_out(row: dict[str, Any]) -> TemplateChangeOut:
    return TemplateChangeOut(
        id=row["id"],
        module=row["module_id"],
        role=row["role_code"],
        level_before=row["level_before"],
        level_after=row["level_after"],
        changed_by=row["changed_by"],
        reason=row["reason"],
        changed_at=row["changed_at"],
    )


router = APIRouter(
    prefix="/platform/default-roles",
    tags=["platform"],
    dependencies=[ROLES_MANAGE, Depends(require_active_tenant)],
)


@router.get(
    "", operation_id="platform_get_default_role_template", response_model=DefaultRoleTemplate
)
async def get_template() -> DefaultRoleTemplate:
    async with with_tenant(get_context()) as conn:
        cells = await list_cells(conn)
    return DefaultRoleTemplate(
        roles=list(ROLE_CODES),
        levels=list(LEVELS),
        cells=[
            TemplateCellOut(
                module=c.module,
                role=c.role,
                level=c.level,
                shipped_level=c.shipped,
                overridden=c.level != c.shipped,
                updated_by=c.updated_by,
                updated_at=c.updated_at,
            )
            for c in cells
        ],
    )


@router.patch(
    "",
    operation_id="platform_patch_default_role_template",
    response_model=TemplateChangeList,
    responses=_ERRORS,
)
async def patch_template(principal: Operator, body: TemplatePatch) -> TemplateChangeList:
    changes = [LevelChange(module=c.module, role=c.role, level=c.level) for c in body.changes]
    async with with_tenant(get_context()) as conn:
        written = await apply_changes(
            conn, changes, actor=principal.actor_id, reason=body.reason.strip()
        )
    return TemplateChangeList(items=[_change_out(row) for row in written])


@router.get(
    "/history",
    operation_id="platform_list_default_role_history",
    response_model=TemplateChangeList,
)
async def get_history(
    module: Annotated[str | None, Query(max_length=64)] = None,
    role: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> TemplateChangeList:
    async with with_tenant(get_context()) as conn:
        rows = await list_history(conn, module=module, role=role, limit=limit)
    return TemplateChangeList(items=[_change_out(row) for row in rows])


@router.post(
    "/sync",
    operation_id="platform_sync_default_roles",
    response_model=SyncResult,
    responses=_ERRORS,
)
async def sync_tenants(body: SyncRequest) -> SyncResult:
    active = await active_tenant_ids()
    if body.tenant_ids is None:
        targets = active
    else:
        targets = list(dict.fromkeys(body.tenant_ids))
        if unknown := sorted(str(t) for t in set(targets) - set(active)):
            raise DomainError(422, "UNKNOWN_TENANT", key=", ".join(unknown))
    out: list[TenantSyncOut] = []
    for tenant in targets:
        ctx = dataclasses.replace(
            get_context(),
            tenant_id=tenant,
            project_id=None,
            tenant_slug=None,
            region_code=None,
            asset_path_scope=(),
        )
        with use_context(ctx):
            async with with_tenant(ctx) as conn:
                report = await seed_default_roles(conn)
        out.append(
            TenantSyncOut(
                tenant_id=tenant,
                created=report.created,
                updated=report.updated,
                pending=report.pending,
                excess=report.excess,
            )
        )
    return SyncResult(tenants=out)
