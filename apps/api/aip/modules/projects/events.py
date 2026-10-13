"""Domain events the projects module publishes (via the outbox, ADR 0003).

``project.created``, ``project.updated`` and ``project.archived`` (all v1) share one payload:
``{projectId, code, status, before, after}``, where ``before``/``after`` hold the changed fields
in camelCase (null on ``project.created``). The models are registered with the platform's
event schemas when this module loads.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import event_schemas

__all__ = ["PROJECT_ARCHIVED", "PROJECT_CREATED", "PROJECT_UPDATED", "ProjectEvent"]

PROJECT_CREATED = "project.created"
PROJECT_UPDATED = "project.updated"
PROJECT_ARCHIVED = "project.archived"


class ProjectEvent(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    project_id: UUID
    code: str
    status: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


for _name in (PROJECT_CREATED, PROJECT_UPDATED, PROJECT_ARCHIVED):
    event_schemas.register(_name, 1, ProjectEvent)
