"""Who may decide a route step (APPROVALS-04), evaluated at decision time and never snapshotted.

``is_eligible(directory, actor_id, approver_type, approver_ref, project_id)``:

- ``user``: ``approver_ref`` is the actor;
- ``role``: the actor holds role ``approver_ref`` tenant-wide or on the instance's project
  (ACCESS-02 assignments, ``access.api.has_role``; team and asset-subtree assignments never count);
- ``team``: the actor is a live member of live team ``approver_ref``, and the team is tenant-level
  or on the instance's project (ACCESS-04, ``access.api.teams_for_user``).

An actor with no user id (a service principal) is never eligible. ``AccessDirectory`` answers
through the access module's published interface on the caller's tenant connection; tests pass a
fake ``ApproverDirectory``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.api import has_role, role_code_for_id, teams_for_user

__all__ = ["AccessDirectory", "ApproverDirectory", "ApproverType", "TeamScope", "is_eligible"]

ApproverType = Literal["user", "role", "team"]


class TeamScope(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def project_id(self) -> UUID | None: ...


class ApproverDirectory(Protocol):
    async def has_role(self, user_id: UUID, role_id: UUID, project_id: UUID | None) -> bool: ...

    async def teams(self, user_id: UUID) -> Sequence[TeamScope]: ...


class AccessDirectory:
    """The access module's answers on the caller's ``with_tenant`` connection."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def has_role(self, user_id: UUID, role_id: UUID, project_id: UUID | None) -> bool:
        code = await role_code_for_id(self._conn, role_id)
        if code is None:
            return False
        return await has_role(self._conn, user_id, code, project_id)

    async def teams(self, user_id: UUID) -> Sequence[TeamScope]:
        return await teams_for_user(self._conn, user_id)


async def is_eligible(
    directory: ApproverDirectory,
    actor_id: UUID | None,
    approver_type: ApproverType,
    approver_ref: UUID,
    project_id: UUID | None,
) -> bool:
    """Whether the actor may decide a step with this approver on an instance in ``project_id``."""
    if actor_id is None:
        return False
    if approver_type == "user":
        return approver_ref == actor_id
    if approver_type == "role":
        return await directory.has_role(actor_id, approver_ref, project_id)
    return any(
        team.id == approver_ref and team.project_id in (None, project_id)
        for team in await directory.teams(actor_id)
    )
