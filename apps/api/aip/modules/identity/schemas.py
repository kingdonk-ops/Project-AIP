"""Pydantic request/response models for identity (IDENTITY-01)."""

from __future__ import annotations

from datetime import datetime
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
    """Same status and keys whether or not the email or domain is known; the tenant is never sent."""

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
