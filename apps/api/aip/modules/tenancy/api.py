"""Published interface of the tenancy module (TENANCY-01 step 5).

Other modules may import only this file, and only these names:

- ``require_active_tenant``: FastAPI dependency for every tenant-scoped route; 401 without a
  principal or a known tenant, 403 for a tenant that is not ``active``;
- ``get_tenant(tenant_id)``: the tenant, read inside ``with_tenant(tenant_id)``, or ``None``;
- ``load_tenant(conn, tenant_id)``: the same read on a connection the caller already holds from
  ``with_tenant`` (IDENTITY-02's sign-in provisioning checks the tenant in its own transaction);
- ``access_for_status(status)`` / ``Denial``: whether a tenant in that status may be used, and if
  not the stable 403 code (unknown statuses deny);
- ``TenantView``: the tenant as other modules see it (no key references).
"""

from __future__ import annotations

from uuid import UUID

from aip.modules.tenancy.dependencies import require_active_tenant
from aip.modules.tenancy.repository import load_tenant
from aip.modules.tenancy.schemas import TenantView
from aip.modules.tenancy.service import Denial, TenantService, access_for_status

__all__ = [
    "Denial",
    "TenantView",
    "access_for_status",
    "get_tenant",
    "load_tenant",
    "require_active_tenant",
]


async def get_tenant(tenant_id: UUID) -> TenantView | None:
    """The live tenant ``tenant_id`` (any status), read inside ``with_tenant``, or ``None``."""
    return await TenantService().get(tenant_id)
