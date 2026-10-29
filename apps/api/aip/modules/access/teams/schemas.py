"""Request and response models for teams and team membership (ACCESS-04), camelCase JSON.

``teamType`` is a stable internal code (``internal``, ``subcontractor``, ``client``); the UI shows
it through terminology keys. A team's project is fixed when it is created.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

__all__ = [
    "MembersAdd",
    "TeamCreate",
    "TeamList",
    "TeamMemberList",
    "TeamMemberOut",
    "TeamOut",
    "TeamType",
    "TeamUpdate",
]

TeamType = Literal["internal", "subcontractor", "client"]
TeamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class TeamCreate(_Model):
    name: TeamName
    team_type: TeamType
    project_id: UUID | None = None
    organisation_id: UUID | None = None


class TeamUpdate(_Model):
    """Every field optional; the project cannot change."""

    name: TeamName | None = None
    team_type: TeamType | None = None
    organisation_id: UUID | None = None


class TeamOut(_Model):
    id: UUID
    name: str
    team_type: TeamType
    project_id: UUID | None
    organisation_id: UUID | None
    scim_group_id: str | None
    member_count: int
    created_at: datetime
    updated_at: datetime


class TeamList(_Model):
    items: list[TeamOut]


class MembersAdd(_Model):
    user_ids: list[UUID] = Field(min_length=1, max_length=500)


class TeamMemberOut(_Model):
    user_id: UUID
    source: Literal["manual", "scim"]
    created_at: datetime


class TeamMemberList(_Model):
    items: list[TeamMemberOut]
