"""HTTP routes for tenancy (TENANCY-01, ENT-01).

- ``GET /api/v1/me/tenant``: the caller's own tenant, guarded by ``require_active_tenant``.
- ``GET /api/v1/settings/plan-and-usage`` (``tenancy.plan.read``): the tenant's plan, features,
  limits and latest usage, read-only (ENT-01 step 7). Nothing here changes a plan.

The operator API that changes subscriptions and overrides is mounted by the ops module
(``aip.modules.ops.platform_tenants``), which owns the ``platform.*`` permissions (ADR 0029).
There is no ``/register`` or other self-signup route (sales-led, operator-provisioned; ADR 0008).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from aip.modules.tenancy.dependencies import require_active_tenant
from aip.modules.tenancy.entitlements.dependencies import get_entitlement_service
from aip.modules.tenancy.entitlements.service import EntitlementService
from aip.modules.tenancy.schemas import PlanAndUsage, TenantErrorResponse, TenantView
from aip.platform.access import authenticated, requires
from aip.platform.context import get_context

router = APIRouter(tags=["tenancy"])

Entitlements = Annotated[EntitlementService, Depends(get_entitlement_service)]


@router.get(
    "/me/tenant",
    dependencies=[Depends(authenticated())],
    response_model=TenantView,
    responses={
        200: {"description": "The caller's active tenant."},
        401: {
            "model": TenantErrorResponse,
            "description": "No authenticated principal, or no known tenant for it.",
        },
        403: {
            "model": TenantErrorResponse,
            "description": "The tenant is suspended, offboarded or not ready.",
        },
    },
)
async def get_my_tenant(
    tenant: Annotated[TenantView, Depends(require_active_tenant)], response: Response
) -> TenantView:
    response.headers["Cache-Control"] = "no-store"
    return tenant


@router.get(
    "/settings/plan-and-usage",
    operation_id="tenancy_plan_and_usage",
    response_model=PlanAndUsage,
    dependencies=[Depends(requires("tenancy.plan.read")), Depends(require_active_tenant)],
)
async def plan_and_usage(entitlements: Entitlements, response: Response) -> PlanAndUsage:
    response.headers["Cache-Control"] = "no-store"
    return await entitlements.plan_and_usage(get_context().tenant_id)
