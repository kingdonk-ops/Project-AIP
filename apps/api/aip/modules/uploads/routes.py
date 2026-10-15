"""HTTP routes for upload sessions (UPLOADS-01), mounted under ``/api/v1``.

Creating a session needs ``uploads.create`` on the body's project (a project-scoped grant is
honoured, so the check is made against the project, not tenant-wide). Confirming and reading status
are requester-bound: another user — even one in the same tenant — gets 404, so a session's
existence is never leaked. A holder of ``uploads.admin`` on the session's project may also read its
status. Every route needs an active tenant.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from aip.modules.tenancy.api import require_active_tenant
from aip.modules.uploads.schemas import (
    SessionCreate,
    SessionCreated,
    SessionStatus,
    UploadErrorBody,
)
from aip.modules.uploads.service import UploadSessionService
from aip.platform.access import AccessPrincipal, PolicyService, Resource, authenticated

__all__ = ["router"]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": UploadErrorBody}}
_INVALID: dict[int | str, dict[str, Any]] = {422: {"description": "Validation error"}}

sessions_router = APIRouter(prefix="/uploads/sessions", tags=["uploads"])


@sessions_router.post(
    "",
    operation_id="uploads_create_session",
    response_model=SessionCreated,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_INVALID,
        400: {"model": UploadErrorBody},
        413: {"model": UploadErrorBody},
        415: {"model": UploadErrorBody},
        429: {"model": UploadErrorBody},
    },
)
async def create_session(
    body: SessionCreate,
    request: Request,
    principal: Annotated[AccessPrincipal, Depends(authenticated())],
) -> SessionCreated:
    policy: PolicyService = request.app.state.access_policy
    resource = Resource(project_id=body.project_id, tenant_id=principal.tenant_id)
    await policy.assert_can(principal, "uploads.create", resource)
    return await UploadSessionService().create_session(body)


@sessions_router.post(
    "/{session_id}/confirm",
    operation_id="uploads_confirm_session",
    response_model=SessionStatus,
    responses={**_NOT_FOUND, 409: {"model": UploadErrorBody}, 422: {"model": UploadErrorBody}},
    dependencies=[Depends(authenticated())],
)
async def confirm_session(session_id: UUID) -> SessionStatus:
    return await UploadSessionService().confirm(session_id)


@sessions_router.get(
    "/{session_id}/status",
    operation_id="uploads_session_status",
    response_model=SessionStatus,
    responses=_NOT_FOUND,
)
async def session_status(
    session_id: UUID,
    request: Request,
    principal: Annotated[AccessPrincipal, Depends(authenticated())],
) -> SessionStatus:
    policy: PolicyService = request.app.state.access_policy

    async def is_admin(project_id: UUID) -> bool:
        resource = Resource(project_id=project_id, tenant_id=principal.tenant_id)
        return (await policy.can(principal, "uploads.admin", resource)).allowed

    return await UploadSessionService().get_status(session_id, is_admin=is_admin)


router = APIRouter(dependencies=[Depends(require_active_tenant)])
router.include_router(sessions_router)
