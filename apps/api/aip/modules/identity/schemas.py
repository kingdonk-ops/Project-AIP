"""Pydantic request/response models for identity (IDENTITY-01, IDENTITY-02)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class LoginStartRequest(_CamelModel):
    email: str = Field(min_length=3, max_length=254)
    return_to: str | None = Field(default=None, max_length=2048)


class LoginStartResponse(_CamelModel):
    """Same status and keys whether or not the email or domain is known; never the tenant."""

    method: Literal["sso", "password"]
    redirect_url: str


class ErrorResponse(BaseModel):
    code: str
    detail: str


class VerifiedExternalIdentity(BaseModel):
    """What a completed Keycloak sign-in proves. Built from a verified ID token, then the tokens
    are dropped. ``tenant_id`` is from the pre-auth login directory, never from a token claim."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID | None
    idp_alias: str | None
    subject: str
    email: str
    email_verified: bool
    acr: str | None
    amr: list[str]
    auth_time: datetime
    kc_sid: str | None
    return_to: str = "/"


# --- GET /api/v1/me (IDENTITY-02) ---------------------------------------------------------------


class MeUser(_CamelModel):
    id: UUID
    email: str
    display_name: str
    user_class: Literal["staff", "field", "portal"]
    status: Literal["invited", "active", "deactivated"]


class MeTenant(_CamelModel):
    id: UUID
    slug: str
    name: str


class MeMembership(_CamelModel):
    id: UUID
    membership_type: Literal["member", "client", "subcontractor", "guest"]
    organisation_id: UUID | None
    valid_from: date
    valid_to: date | None


class MeResponse(_CamelModel):
    """The caller's own user, tenant and memberships. Never another tenant's data."""

    user: MeUser
    tenant: MeTenant
    memberships: list[MeMembership]
    aal: Literal[1, 2]
    amr: list[str]


class AuthErrorBody(BaseModel):
    code: str
    message: str


class AuthErrorResponse(BaseModel):
    """Body of a 401/403 on an authenticated route. Never names a tenant or a user."""

    detail: AuthErrorBody
