"""Data access for tenancy (TENANCY-01).

Receives the tenant-bound connection from ``with_tenant`` and never creates its own (ADR 0002).
RLS already limits ``tenants`` to the bound tenant's row; the ``id`` filter and the soft-delete
filter are a second line, not the isolation itself.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.tenancy.schemas import TenantView
from aip.modules.tenancy.tables import tenants

_COLUMNS = (
    tenants.c.id,
    tenants.c.name,
    tenants.c.slug,
    tenants.c.region_code,
    tenants.c.deployment_shape,
    tenants.c.status,
)


async def load_tenant(conn: AsyncConnection, tenant_id: UUID) -> TenantView | None:
    """The live (not soft-deleted) tenant ``tenant_id`` as visible on ``conn``, or ``None``."""
    stmt = select(*_COLUMNS).where(tenants.c.id == tenant_id, tenants.c.deleted_at.is_(None))
    row = (await conn.execute(stmt)).mappings().first()
    if row is None:
        return None
    return TenantView.model_validate(dict(row))
