"""Published interface of the tenancy module (TENANCY-01 step 5).

Other modules may import only this file, and only these three names:

- ``require_active_tenant``: FastAPI dependency for every tenant-scoped route; 401 without a
  principal or a known tenant, 403 for a tenant that is not ``active``;
- ``get_tenant(tenant_id)``: the tenant, read inside ``with_tenant(tenant_id)``, or ``None``;
- ``TenantView``: the tenant as other modules see it (no key references).
"""

from __future__ import annotations

from uuid import UUID

from aip.modules.tenancy.dependencies import require_active_tenant
from aip.modules.tenancy.schemas import TenantView
from aip.modules.tenancy.service import TenantService

__all__ = ["TenantView", "get_tenant", "require_active_tenant"]


async def get_tenant(tenant_id: UUID) -> TenantView | None:
    """The live tenant ``tenant_id`` (any status), read inside ``with_tenant``, or ``None``."""
    return await TenantService().get(tenant_id)
