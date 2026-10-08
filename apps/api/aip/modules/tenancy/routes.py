"""HTTP routes for tenancy (TENANCY-01).

- ``GET /api/v1/me/tenant``: the caller's own tenant, guarded by ``require_active_tenant``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from aip.modules.tenancy.dependencies import require_active_tenant
from aip.modules.tenancy.schemas import TenantErrorResponse, TenantView

router = APIRouter(tags=["tenancy"])


@router.get(
    "/me/tenant",
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
