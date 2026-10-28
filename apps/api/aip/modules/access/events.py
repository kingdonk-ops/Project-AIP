"""Domain events access publishes (via the outbox, ADR 0003) and the events it subscribes to.

Published:

- ``access.role.changed`` v1 (ACCESS-02): ``{roleId, code, action, before, after}``. ``action`` is
  one of ``created``, ``updated``, ``deleted``, ``reset`` or ``seeded``; ``before``/``after`` are
  the sorted permission sets (null when the role did not or no longer exists). The actor is the
  event's ``actor_id``. The audit module (AUDIT-01) records these.
- ``access.role_assignment.created`` / ``access.role_assignment.removed``: v1 (ACCESS-02,
  ``{assignmentId, userId, roleId, roleCode, scopeType, projectId, validTo, approvedBy}``) is
  released and no longer emitted; ACCESS-04 emits v2, which adds ``teamId`` and makes ``userId``
  null for a ``team`` assignment.
- ``access.team.changed`` v1 (ACCESS-04): ``{teamId, action, name, teamType, projectId}``,
  ``action`` one of ``created``, ``updated``, ``deleted``.
- ``team.membership_changed`` v1 (ACCESS-04): ``{teamId, userIds, change}``, ``change`` one of
  ``added`` or ``removed``; ``userIds`` are the users whose membership actually changed.
- ``access.grants_changed`` v1 (ACCESS-04): ``{userIds}``, the users whose grants may have
  changed, or null for the whole tenant (a role's permissions changed).

Subscribed (ARCH-07, idempotent on ``event.id``):

- ``team.membership_changed`` and ``access.grants_changed``: bump the policy cache versions
  (``policy_cache``), so every API instance drops the affected users' cached grants within one
  dispatcher cycle, including when the writing request's own after-commit bump was lost.
- ``user.deactivated`` (IDENTITY-05, ``{userId}``): soft-delete the user's team memberships and
  role assignments (``teams.service.revoke_user_access``), which emits the events above.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.policy_cache import get_policy_cache
from aip.platform.events import register_event
from aip.platform.events.subscribers import DomainEvent, subscriber

__all__ = [
    "GRANTS_CHANGED",
    "ROLE_ASSIGNMENT_CREATED",
    "ROLE_ASSIGNMENT_REMOVED",
    "ROLE_ASSIGNMENT_VERSION",
    "ROLE_CHANGED",
    "TEAM_CHANGED",
    "TEAM_MEMBERSHIP_CHANGED",
    "USER_DEACTIVATED",
    "GrantsChangedEvent",
    "RoleAssignmentEvent",
    "RoleAssignmentEventV2",
    "RoleChangedEvent",
    "TeamChangedEvent",
    "TeamMembershipChangedEvent",
]

ROLE_CHANGED: Final = "access.role.changed"
ROLE_ASSIGNMENT_CREATED: Final = "access.role_assignment.created"
ROLE_ASSIGNMENT_REMOVED: Final = "access.role_assignment.removed"
ROLE_ASSIGNMENT_VERSION: Final = 2  # the version ACCESS-04 emits
TEAM_CHANGED: Final = "access.team.changed"
TEAM_MEMBERSHIP_CHANGED: Final = "team.membership_changed"
GRANTS_CHANGED: Final = "access.grants_changed"
USER_DEACTIVATED: Final = "user.deactivated"  # published by identity (IDENTITY-05)

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
    """v1 (released, no longer emitted)."""

    model_config = _CONFIG

    assignment_id: UUID
    user_id: UUID
    role_id: UUID
    role_code: str
    scope_type: str
    project_id: UUID | None = None
    valid_to: datetime | None = None
    approved_by: UUID | None = None


class RoleAssignmentEventV2(BaseModel):
    """v2: a ``team`` assignment has ``teamId`` and a null ``userId``."""

    model_config = _CONFIG

    assignment_id: UUID
    user_id: UUID | None = None
    team_id: UUID | None = None
    role_id: UUID
    role_code: str
    scope_type: str
    project_id: UUID | None = None
    valid_to: datetime | None = None
    approved_by: UUID | None = None


class TeamChangedEvent(BaseModel):
    model_config = _CONFIG

    team_id: UUID
    action: Literal["created", "updated", "deleted"]
    name: str
    team_type: str
    project_id: UUID | None = None


class TeamMembershipChangedEvent(BaseModel):
    model_config = _CONFIG

    team_id: UUID
    user_ids: list[UUID]
    change: Literal["added", "removed"]


class GrantsChangedEvent(BaseModel):
    model_config = _CONFIG

    user_ids: list[UUID] | None


register_event(ROLE_CHANGED, 1, RoleChangedEvent, "access")
for _name in (ROLE_ASSIGNMENT_CREATED, ROLE_ASSIGNMENT_REMOVED):
    register_event(_name, 1, RoleAssignmentEvent, "access")
    register_event(_name, ROLE_ASSIGNMENT_VERSION, RoleAssignmentEventV2, "access")
register_event(TEAM_CHANGED, 1, TeamChangedEvent, "access")
register_event(TEAM_MEMBERSHIP_CHANGED, 1, TeamMembershipChangedEvent, "access")
register_event(GRANTS_CHANGED, 1, GrantsChangedEvent, "access")


def _user_ids(raw: object) -> list[UUID] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("userIds must be a list or null")
    return [UUID(str(value)) for value in raw]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


@subscriber(TEAM_MEMBERSHIP_CHANGED, 1)
async def bump_on_membership_changed(conn: AsyncConnection, event: DomainEvent) -> None:
    users = _user_ids(event.payload["userIds"]) or []
    await get_policy_cache().bump(event.tenant_id, users)


@subscriber(GRANTS_CHANGED, 1)
async def bump_on_grants_changed(conn: AsyncConnection, event: DomainEvent) -> None:
    await get_policy_cache().bump(event.tenant_id, _user_ids(event.payload.get("userIds")))


@subscriber(USER_DEACTIVATED, 1)
async def revoke_on_user_deactivated(conn: AsyncConnection, event: DomainEvent) -> None:
    # Imported here: the service imports this module's event names.
    from aip.modules.access.teams.service import revoke_user_access

    await revoke_user_access(conn, UUID(str(event.payload["userId"])))
