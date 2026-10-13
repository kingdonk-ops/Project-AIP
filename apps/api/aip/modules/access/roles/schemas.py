"""Request and response models for roles and role assignments (ACCESS-02), camelCase JSON."""

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
    """``tenant``, or ``project`` with ``projectId``. ``team`` and ``asset_subtree`` -> 400."""

    type: Literal["tenant", "project", "team", "asset_subtree"]
    project_id: UUID | None = None

    @model_validator(mode="after")
    def _project_id_matches_type(self) -> Scope:
        if self.type == "project" and self.project_id is None:
            raise ValueError("a project scope needs projectId")
        if self.type == "tenant" and self.project_id is not None:
            raise ValueError("a tenant scope has no projectId")
        return self


class AssignmentCreate(_Model):
    user_id: UUID
    role_id: UUID
    scope: Scope
    valid_to: datetime | None = None


class AssignmentOut(_Model):
    id: UUID
    user_id: UUID
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
