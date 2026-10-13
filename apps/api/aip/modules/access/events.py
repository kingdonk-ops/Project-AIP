"""Domain events access publishes (via the outbox, ADR 0003), all v1. ACCESS-02.

- ``access.role.changed``: ``{roleId, code, action, before, after}``. ``action`` is one of
  ``created``, ``updated``, ``deleted``, ``reset`` or ``seeded``; ``before``/``after`` are the
  sorted permission sets (null when the role did not or no longer exists). The actor is the
  event's ``actor_id``. The audit module (AUDIT-01) records these.
- ``access.role_assignment.created`` / ``access.role_assignment.removed``:
  ``{assignmentId, userId, roleId, roleCode, scopeType, projectId, validTo, approvedBy}``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import event_schemas

__all__ = [
    "ROLE_ASSIGNMENT_CREATED",
    "ROLE_ASSIGNMENT_REMOVED",
    "ROLE_CHANGED",
    "RoleAssignmentEvent",
    "RoleChangedEvent",
]

ROLE_CHANGED = "access.role.changed"
ROLE_ASSIGNMENT_CREATED = "access.role_assignment.created"
ROLE_ASSIGNMENT_REMOVED = "access.role_assignment.removed"

_CONFIG = ConfigDict(
    alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
)


class RoleChangedEvent(BaseModel):
    model_config = _CONFIG

    role_id: UUID
    code: str
    action: Literal["created", "updated", "deleted", "reset", "seeded"]
    before: list[str] | None = None
    after: list[str] | None = None


class RoleAssignmentEvent(BaseModel):
    model_config = _CONFIG

    assignment_id: UUID
    user_id: UUID
    role_id: UUID
    role_code: str
    scope_type: str
    project_id: UUID | None = None
    valid_to: datetime | None = None
    approved_by: UUID | None = None


event_schemas.register(ROLE_CHANGED, 1, RoleChangedEvent)
for _name in (ROLE_ASSIGNMENT_CREATED, ROLE_ASSIGNMENT_REMOVED):
    event_schemas.register(_name, 1, RoleAssignmentEvent)
