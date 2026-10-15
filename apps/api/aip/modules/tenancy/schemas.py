"""Pydantic models for tenancy (TENANCY-01, ENT-01).

``TenantView`` is published through ``api.py``. It never carries ``kms_key_ref``. ENT-01 adds the
subscription, override and plan-and-usage models (camelCase JSON; no price, invoice or payment
field anywhere, ADR 0008).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
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


# --- ENT-01: entitlements (ADR 0008/0017/0023) -----------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ContractRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Code = Annotated[str, StringConstraints(min_length=1, max_length=50)]
SubscriptionTerm = Literal["annual", "multi_year", "trial", "sandbox"]
SubscriptionStatus = Literal["active", "expired", "suspended"]
SeatClass = Literal["full", "portal"]
EntitlementSource = Literal["plan", "add_on", "override", "toggle", "none"]
LimitActionName = Literal["BLOCK", "WARN", "OVERAGE"]
Count = Annotated[int, Field(ge=0)]


class SubscriptionPut(_Model):
    """An operator sets the subscription; ``contract_ref`` is required for production terms."""

    plan_code: Code
    plan_version: Annotated[int, Field(ge=1)] | None = None
    term: SubscriptionTerm
    starts_on: date
    ends_on: date | None = None
    renewal_date: date | None = None
    seat_limits: dict[SeatClass, Count | None] = {}
    storage_gb: Count | None = None
    add_ons: list[Code] = []
    contract_ref: ContractRef | None = None
    status: SubscriptionStatus = "active"
    reason: Reason


class SubscriptionOut(_Model):
    tenant_id: UUID
    plan_code: str
    plan_version: int
    term: SubscriptionTerm
    starts_on: date
    ends_on: date | None
    renewal_date: date | None
    seat_limits: dict[str, int | None]
    storage_gb: int | None
    add_ons: list[str]
    contract_ref: str | None
    status: SubscriptionStatus
    entitlement_version: int


class OverrideCreate(_Model):
    """A boolean for ``feature.*``; a count, or null for unlimited, for ``limit.*``."""

    key: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    value: bool | Count | None
    reason: Reason
    expires_at: AwareDatetime | None = None


class OverrideOut(_Model):
    id: UUID
    key: str
    value: bool | int | None
    reason: str
    expires_at: datetime | None
    created_at: datetime


class FeatureOut(_Model):
    key: str
    enabled: bool
    source: EntitlementSource


class LimitOut(_Model):
    """``limit`` null is unlimited; ``used`` null means nothing measures it yet."""

    key: str
    limit: int | None
    used: float | None
    action: LimitActionName
    source: EntitlementSource


class DbEstimate(_Model):
    bytes: int
    method: str
    captured_at: datetime


class PlanAndUsage(_Model):
    """The read-only "Plan and usage" page. No prices, invoices or payment data."""

    plan: str | None
    plan_version: int | None
    term: SubscriptionTerm | None
    status: SubscriptionStatus | None
    renewal_date: date | None
    contract_ref: str | None
    usage_period: date | None
    features: list[FeatureOut]
    limits: list[LimitOut]
    db_estimate: DbEstimate | None


class EntitlementErrorBody(BaseModel):
    """403 ``NOT_ENTITLED`` / ``LIMIT_REACHED``, 422 ``CONTRACT_REF_REQUIRED`` and the like."""

    code: str
    key: str | None = None
