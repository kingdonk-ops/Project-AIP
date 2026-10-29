"""Request and response models for roles and role assignments (ACCESS-02), camelCase JSON.

ACCESS-04: an assignment may target a team (``{"type": "team", "teamId": ...}``). ``Scope`` and
``AssignmentCreate`` mirror the ``ck_role_assignment_scope`` CHECK: a team scope names a team, no
project and no user; every other scope names a user.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from aip.modules.access.schemas import PermissionCode

__all__ = [
    "AccessErrorBody",
    "AssignmentCreate",
    "AssignmentList",
    "AssignmentOut",
    "RoleClone",
    "RoleCreate",
    "RoleList",
    "RoleOut",
    "RoleUpdate",
    "Scope",
]

_CODE = r"^[a-z][a-z0-9_]{1,62}$"


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class AccessErrorBody(_Model):
    code: str


class RoleOut(_Model):
    id: UUID
    code: str
    name: str | None
    name_term_key: str | None
    is_system: bool
    customised_at: datetime | None
    permissions: list[PermissionCode]


class RoleList(_Model):
    items: list[RoleOut]


class RoleCreate(_Model):
    code: str = Field(pattern=_CODE)
    name: str = Field(min_length=1, max_length=120)
    permissions: list[PermissionCode] = Field(max_length=500)


class RoleUpdate(_Model):
    """Every field optional. A system role keeps its code and name (409 SYSTEM_ROLE_IMMUTABLE)."""

    code: str | None = Field(default=None, pattern=_CODE)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    permissions: list[PermissionCode] | None = Field(default=None, max_length=500)


class RoleClone(_Model):
    code: str = Field(pattern=_CODE)
    name: str = Field(min_length=1, max_length=120)


class Scope(_Model):
    """``tenant``; ``project`` with ``projectId``; ``team`` with ``teamId`` (ACCESS-04).
    ``asset_subtree`` -> 400."""

    type: Literal["tenant", "project", "team", "asset_subtree"]
    project_id: UUID | None = None
    team_id: UUID | None = None

    @model_validator(mode="after")
    def _ids_match_type(self) -> Scope:
        if self.type == "project" and self.project_id is None:
            raise ValueError("a project scope needs projectId")
        if self.type == "tenant" and self.project_id is not None:
            raise ValueError("a tenant scope has no projectId")
        if self.type == "team" and (self.team_id is None or self.project_id is not None):
            raise ValueError("a team scope needs teamId and no projectId (it is the team's)")
        if self.type != "team" and self.team_id is not None:
            raise ValueError("only a team scope has a teamId")
        return self


class AssignmentCreate(_Model):
    """A team scope names no user (its members hold the role); every other scope needs userId."""

    user_id: UUID | None = None
    role_id: UUID
    scope: Scope
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def _holder_matches_scope(self) -> AssignmentCreate:
        if self.scope.type == "team" and self.user_id is not None:
            raise ValueError("a team assignment has no userId")
        if self.scope.type != "team" and self.user_id is None:
            raise ValueError("userId is required")
        return self


class AssignmentOut(_Model):
    id: UUID
    user_id: UUID | None
    team_id: UUID | None = None
    role_id: UUID
    role_code: str
    scope_type: str
    project_id: UUID | None
    source: str
    valid_from: datetime
    valid_to: datetime | None
    approved_by: UUID | None
    created_by: UUID | None
    created_at: datetime


class AssignmentList(_Model):
    items: list[AssignmentOut]
