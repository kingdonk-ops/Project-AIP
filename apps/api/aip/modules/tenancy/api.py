"""Published interface of the tenancy module (TENANCY-01 step 5).

Other modules may import only this file, and only these names:

- ``require_active_tenant``: FastAPI dependency for every tenant-scoped route; 401 without a
  principal or a known tenant, 403 for a tenant that is not ``active``;
- ``get_tenant(tenant_id)``: the tenant, read inside ``with_tenant(tenant_id)``, or ``None``;
- ``load_tenant(conn, tenant_id)``: the same read on a connection the caller already holds from
  ``with_tenant`` (IDENTITY-02's sign-in provisioning checks the tenant in its own transaction);
- ``access_for_status(status)`` / ``Denial``: whether a tenant in that status may be used, and if
  not the stable 403 code (unknown statuses deny);
- ``TenantView``: the tenant as other modules see it (no key references);
- ``region_exists(conn, code)``: whether ``code`` is a deployment region (PROJECTS-01);
- ``assert_demo_has_no_real_customers`` / ``RealDataInDemoError`` / ``DEMO_ENV``: the demo
  deployment's startup guard (OPS-11); the app refuses to start in ``demo`` when any tenant is
  flagged as a real customer.
- Entitlements (ENT-01, ADR 0008/0023): ``EntitlementService`` (``check``, ``check_limit``,
  ``check_seat``, ``list``) with ``Decision`` / ``LimitDecision`` and ``InvalidEntitlementKey``;
  the route dependency ``requires_entitlement`` and ``ensure_within_limit`` (403 ``NOT_ENTITLED``
  / ``LIMIT_REACHED``); ``get_entitlement_service``; and the registries other modules plug into:
  ``register_toggle_provider`` (``ScopeToggleProvider``, projects) and ``register_usage_source``
  (``UsageSource`` / ``UsageFigures``, identity and uploads); and the operator request and
  response models (``SubscriptionPut``/``Out``, ``OverrideCreate``/``Out``,
  ``EntitlementErrorBody``) for the ops module's operator routes.
"""

from __future__ import annotations

from uuid import UUID

from aip.modules.tenancy.demo_guard import (
    DEMO_ENV,
    RealDataInDemoError,
    assert_demo_has_no_real_customers,
)
from aip.modules.tenancy.dependencies import require_active_tenant
from aip.modules.tenancy.entitlements.dependencies import (
    ensure_within_limit,
    get_entitlement_service,
    requires_entitlement,
)
from aip.modules.tenancy.entitlements.resolve import InvalidEntitlementKey, LimitDecision
from aip.modules.tenancy.entitlements.service import (
    Decision,
    EntitlementService,
    ScopeToggleProvider,
    register_toggle_provider,
)
from aip.modules.tenancy.entitlements.usage import (
    UsageFigures,
    UsageSource,
    register_usage_source,
)
from aip.modules.tenancy.repository import load_tenant, region_exists
from aip.modules.tenancy.schemas import (
    EntitlementErrorBody,
    OverrideCreate,
    OverrideOut,
    SubscriptionOut,
    SubscriptionPut,
    TenantView,
)
from aip.modules.tenancy.service import Denial, TenantService, access_for_status

__all__ = [
    "DEMO_ENV",
    "Decision",
    "Denial",
    "EntitlementErrorBody",
    "EntitlementService",
    "InvalidEntitlementKey",
    "LimitDecision",
    "OverrideCreate",
    "OverrideOut",
    "RealDataInDemoError",
    "ScopeToggleProvider",
    "SubscriptionOut",
    "SubscriptionPut",
    "TenantView",
    "UsageFigures",
    "UsageSource",
    "access_for_status",
    "assert_demo_has_no_real_customers",
    "ensure_within_limit",
    "get_entitlement_service",
    "get_tenant",
    "load_tenant",
    "region_exists",
    "register_toggle_provider",
    "register_usage_source",
    "require_active_tenant",
    "requires_entitlement",
]


async def get_tenant(tenant_id: UUID) -> TenantView | None:
    """The live tenant ``tenant_id`` (any status), read inside ``with_tenant``, or ``None``."""
    return await TenantService().get(tenant_id)
