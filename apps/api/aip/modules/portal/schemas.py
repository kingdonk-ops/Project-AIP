"""Pydantic request/response models for portal users and grants (PORTAL-01).

JSON uses camelCase (``companyName``). Request bodies are strict (``extra="forbid"``),
so a client can never set an expiry, a status or a role. A grant's ``actions`` are 1 to 4 distinct
codes of ``view``/``sign_off``/``witness``/``download`` and always include ``view``.

PORTAL-02: ``PortalMeOut`` is what a signed-in client sees of itself (``GET /api/v1/portal/me``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

from aip.modules.portal.policies import (
    MAX_GRANTS_PER_INVITE,
    Action,
    EffectiveStatus,
    GrantState,
    PortalUserStatus,
)

__all__ = [
    "GrantIn",
    "GrantOut",
    "InviteIn",
    "PortalErrorBody",
    "PortalMeOut",
    "PortalProjectOut",
    "PortalUserOut",
    "PortalUserPage",
    "SuspendIn",
]

_Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response: built from database rows, so columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class PortalErrorBody(_Out):
    """A domain error: a stable ``code`` (``PROJECT_CLOSED``, ``REVOKED``, ``GRANT_EXISTS``)."""

    code: str


class GrantIn(_Model):
    project_id: UUID
    asset_id: UUID | None = None
    actions: list[Action] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def _view_and_distinct(self) -> Self:
        if len(set(self.actions)) != len(self.actions):
            raise ValueError("actions must not repeat")
        if "view" not in self.actions:
            raise ValueError("actions must include view")
        return self


class InviteIn(_Model):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]
    first_name: _Name
    last_name: _Name
    company_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    organisation_id: UUID | None = None
    grants: list[GrantIn] = Field(min_length=1, max_length=MAX_GRANTS_PER_INVITE)


class SuspendIn(_Model):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class GrantOut(_Out):
    id: UUID
    project_id: UUID
    asset_id: UUID | None
    actions: list[str]
    access_days: int
    expires_at: datetime
    state: GrantState
    renewed_at: datetime | None
    renewed_by: UUID | None
    revoked_at: datetime | None
    revoked_reason: str | None
    created_by: UUID
    created_at: datetime


class PortalUserOut(_Out):
    """A portal user with their grants that are not revoked (live and expired).

    ``expiresAt`` is the latest expiry among the live grants (``null`` with none).
    """

    id: UUID
    user_id: UUID
    email: str | None
    company_name: str
    organisation_id: UUID | None
    status: PortalUserStatus
    effective_status: EffectiveStatus
    invited_by: UUID
    first_signed_in_at: datetime | None
    suspended_at: datetime | None
    suspended_reason: str | None
    expires_at: datetime | None
    grants: list[GrantOut]
    sync_version: int
    created_at: datetime
    updated_at: datetime


class PortalUserPage(_Out):
    items: list[PortalUserOut]
    next_cursor: str | None


class PortalProjectOut(_Out):
    """A project the client may act on now, with the grant actions it holds there."""

    id: UUID
    code: str
    name: str
    actions: list[Action]


class PortalMeOut(_Out):
    """The signed-in client (PORTAL-02): ``projects`` is empty unless ``effectiveStatus`` is
    ``active``."""

    user_id: UUID
    display_name: str | None
    company_name: str
    effective_status: EffectiveStatus
    projects: list[PortalProjectOut]
