"""Pydantic request/response models for identity (IDENTITY-01 to IDENTITY-04)."""

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


class StepUpState(BaseModel):
    """The session a step-up sign-in elevates and when it started (from the sealed cookie)."""

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    started_at: datetime


class VerifiedExternalIdentity(BaseModel):
    """What a completed Keycloak sign-in proves. Built from a verified ID token, then the tokens
    are dropped. ``tenant_id`` is from the pre-auth login directory, never from a token claim.

    ``upstream_amr`` is the customer IdP's ``amr`` for a brokered sign-in (IDENTITY-04: imported by
    the IdP mapper, emitted as the ``upstream_amr`` claim); ``step_up`` is set when this sign-in
    was a step-up rather than a login. ``audience`` (IDENTITY-10) is the flow that signed in:
    ``app`` (staff, ``aip-api``) or ``portal`` (clients, ``aip-portal``).
    """

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
    upstream_amr: list[str] = Field(default_factory=list[str])
    step_up: StepUpState | None = None
    audience: Literal["app", "portal"] = "app"

    @property
    def aal(self) -> Literal[1, 2]:

        from aip.modules.identity.sessions import derive_aal

        return derive_aal(self.acr, self.amr, self.upstream_amr)

    @property
    def session_amr(self) -> list[str]:
        """The ``amr`` the app session records: Keycloak's, plus for a brokered sign-in ``fed``
        and the upstream IdP's values (sign-off assurance reads the method from them)."""
        if self.idp_alias is None:
            return list(self.amr)
        return sorted({*self.amr, "fed", *self.upstream_amr})[:16]


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


# --- sessions (IDENTITY-03) ----------------------------------------------------------------------


class SessionOut(_CamelModel):
    """One of the caller's own live sessions (the "Active sessions" page)."""

    id: UUID
    current: bool
    audience: Literal["app", "portal", "device"]
    aal: Literal[1, 2]
    ip: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime


class SessionList(_CamelModel):
    items: list[SessionOut]


# --- invites, MFA reset and sign-off policy (IDENTITY-04) ---------------------------------------


class InviteCreate(_CamelModel):
    email: str = Field(min_length=3, max_length=254)
    user_class: Literal["staff"] = "staff"
    organisation_id: UUID | None = None
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)


class InviteCreated(_CamelModel):
    invite_id: UUID
    user_id: UUID
    method: Literal["local", "sso"]


class InviteOut(_CamelModel):
    id: UUID
    user_id: UUID
    email: str
    user_class: Literal["staff", "field", "portal"]
    method: Literal["local", "sso"]
    status: Literal["pending", "sent", "accepted", "revoked", "failed"]
    last_error: str | None
    expires_at: datetime
    sent_at: datetime | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InviteList(_CamelModel):
    items: list[InviteOut]


class StepUpErrorBody(BaseModel):
    code: Literal["STEP_UP_REQUIRED"]
    message: str
    stepUpUrl: str  # noqa: N815 - the wire name


class StepUpErrorResponse(BaseModel):
    """401 from a critical action: confirm with a second factor at ``stepUpUrl``, then retry."""

    detail: StepUpErrorBody


class SignoffPolicyOut(_CamelModel):
    action_code: str
    min_aal: Literal[1, 2]
    step_up_max_age_min: int
    is_default: bool
    updated_at: datetime | None = None


class SignoffPolicyList(_CamelModel):
    items: list[SignoffPolicyOut]


class SignoffPolicyUpdate(_CamelModel):
    action_code: str = Field(
        min_length=3, max_length=100, pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$"
    )
    min_aal: Literal[1, 2]
    step_up_max_age_min: int = Field(default=10, ge=1, le=60)
