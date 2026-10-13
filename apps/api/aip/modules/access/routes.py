"""HTTP routes for access (ACCESS-01).

- ``GET /api/v1/access/me/abilities?projectId=``: ``authenticated()``. The caller's permission
  codes for the tenant, or for one project when ``projectId`` is given (tenant grants plus that
  project's grants). The UI uses it to hide actions; the API still checks every call.
- ACCESS-02: roles and role assignments (``aip.modules.access.roles.routes``).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from aip.modules.access.roles.routes import router as roles_router
from aip.modules.access.schemas import AbilitiesResponse
from aip.platform.access import AccessPrincipal, PolicyService, Resource, authenticated

router = APIRouter(prefix="/access", tags=["access"])


@router.get(
    "/me/abilities",
    response_model=AbilitiesResponse,
    responses={401: {"description": "No authenticated principal."}},
)
async def get_my_abilities(
    request: Request,
    response: Response,
    principal: Annotated[AccessPrincipal, Depends(authenticated())],
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
) -> AbilitiesResponse:
    policy: PolicyService | None = getattr(request.app.state, "access_policy", None)
    if policy is None:  # access not installed: nothing is allowed
        raise HTTPException(status_code=503, detail="access policy is not available")
    codes = await policy.allowed_permissions(principal, Resource(project_id=project_id))
    response.headers["Cache-Control"] = "no-store"
    return AbilitiesResponse(permissions=codes)


router.include_router(roles_router)
