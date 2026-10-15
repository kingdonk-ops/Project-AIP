"""Operator API for tenant entitlements (ENT-01 step 7, ADR 0008/0017/0023, ADR 0029).

Platform operators only (``platform.tenants.manage``, privileged; the ops module owns the
``platform`` permission namespace per ADR 0029). Every call carries a ``reason``, and the change is
written by tenancy's ``EntitlementService`` with its ``tenant.entitlements_changed`` audit event:

- ``PUT /api/v1/platform/tenants/{tenant_id}/subscription``: plan, term, dates, contracted seats
  and storage, add-ons, ``contract_ref`` (required for annual and multi-year terms, 422
  ``CONTRACT_REF_REQUIRED``) and status;
- ``POST /api/v1/platform/tenants/{tenant_id}/entitlement-overrides``: one key's value, with an
  optional expiry;
- ``DELETE /api/v1/platform/tenants/{tenant_id}/entitlement-overrides/{override_id}?reason=``.

The operator's own tenant must be active; the target tenant comes from the path and must exist.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from aip.modules.tenancy.api import (
    EntitlementErrorBody,
    EntitlementService,
    OverrideCreate,
    OverrideOut,
    SubscriptionOut,
    SubscriptionPut,
    get_entitlement_service,
    require_active_tenant,
)
from aip.platform.access import requires

__all__ = ["router"]

Entitlements = Annotated[EntitlementService, Depends(get_entitlement_service)]

_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": EntitlementErrorBody, "description": "No such tenant or override."},
    422: {"model": EntitlementErrorBody, "description": "Invalid plan, key, value or contract."},
}

router = APIRouter(
    prefix="/platform/tenants",
    tags=["platform"],
    dependencies=[Depends(requires("platform.tenants.manage")), Depends(require_active_tenant)],
)


@router.put(
    "/{tenant_id}/subscription",
    operation_id="platform_put_tenant_subscription",
    response_model=SubscriptionOut,
    responses=_ERRORS,
)
async def put_subscription(
    tenant_id: UUID, body: SubscriptionPut, entitlements: Entitlements
) -> SubscriptionOut:
    return await entitlements.put_subscription(tenant_id, body)


@router.post(
    "/{tenant_id}/entitlement-overrides",
    operation_id="platform_add_entitlement_override",
    response_model=OverrideOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
)
async def add_override(
    tenant_id: UUID, body: OverrideCreate, entitlements: Entitlements
) -> OverrideOut:
    return await entitlements.add_override(tenant_id, body)


@router.delete(
    "/{tenant_id}/entitlement-overrides/{override_id}",
    operation_id="platform_remove_entitlement_override",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=_ERRORS,
)
async def remove_override(
    tenant_id: UUID,
    override_id: UUID,
    entitlements: Entitlements,
    reason: Annotated[str, Query(min_length=1, max_length=500, pattern=r"\S")],
) -> Response:
    await entitlements.remove_override(tenant_id, override_id, reason.strip())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
