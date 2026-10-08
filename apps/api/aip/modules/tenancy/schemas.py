"""Pydantic models for tenancy (TENANCY-01).

``TenantView`` is published through ``api.py``. It never carries ``kms_key_ref``.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

TenantStatus = Literal["provisioning", "active", "suspended", "offboarding", "offboarded"]
DeploymentShape = Literal["pooled", "siloed"]


class TenantView(BaseModel):
    """The caller's tenant as other modules and the API see it."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )

    id: UUID
    name: str
    slug: str
    region_code: str
    deployment_shape: DeploymentShape
    status: TenantStatus


class TenantErrorBody(BaseModel):
    code: str
    message: str


class TenantErrorResponse(BaseModel):
    """Body of a 401/403 from ``require_active_tenant``. Never names the tenant."""

    detail: TenantErrorBody
