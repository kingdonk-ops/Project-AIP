"""HTTP routes for organisations (TENANCY-03), mounted under ``/api/v1/settings/organisations``.

Reads need ``tenancy.organisation.read`` (tenant admin, project manager, auditor by default);
changes need ``tenancy.organisation.manage`` (tenant admin). Deactivate is a PATCH of ``status``.
Explicit ``operation_id``s keep the generated client's hook names stable.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from aip.modules.tenancy.organisations.schemas import (
    OrganisationCreate,
    OrganisationErrorBody,
    OrganisationList,
    OrganisationOut,
    OrganisationStatus,
    OrganisationType,
    OrganisationUpdate,
)
from aip.modules.tenancy.organisations.service import OrganisationService
from aip.platform.access import requires

__all__ = ["router"]

READ = "tenancy.organisation.read"
MANAGE = "tenancy.organisation.manage"

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": OrganisationErrorBody}}
_CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": OrganisationErrorBody}}
_INVALID: dict[int | str, dict[str, Any]] = {422: {"description": "Validation error"}}

router = APIRouter(prefix="/settings/organisations", tags=["organisations"])


@router.get(
    "",
    operation_id="organisations_list",
    response_model=OrganisationList,
    responses=_INVALID,
    dependencies=[Depends(requires(READ))],
)
async def list_organisations(
    type_: Annotated[list[OrganisationType], Query(alias="type")] = [],  # noqa: B006 - FastAPI copies it
    status_: Annotated[list[OrganisationStatus], Query(alias="status")] = [],  # noqa: B006
) -> OrganisationList:
    return await OrganisationService().list(types=type_, statuses=status_)


@router.get(
    "/{organisation_id}",
    operation_id="organisations_get",
    response_model=OrganisationOut,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires(READ))],
)
async def get_organisation(organisation_id: UUID) -> OrganisationOut:
    return await OrganisationService().get(organisation_id)


@router.post(
    "",
    operation_id="organisations_create",
    response_model=OrganisationOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_CONFLICT, **_INVALID},
    dependencies=[Depends(requires(MANAGE))],
)
async def create_organisation(body: OrganisationCreate) -> OrganisationOut:
    return await OrganisationService().create(body)


@router.patch(
    "/{organisation_id}",
    operation_id="organisations_update",
    response_model=OrganisationOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires(MANAGE))],
)
async def update_organisation(organisation_id: UUID, body: OrganisationUpdate) -> OrganisationOut:
    return await OrganisationService().update(organisation_id, body)
