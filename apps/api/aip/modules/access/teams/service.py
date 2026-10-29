"""Teams and team membership (ACCESS-04).

Who may manage a team: a holder of ``access.team.manage`` at tenant scope manages every team; a
holder of it on a project manages that project's teams (checked here through ``PolicyService``,
deny by default) [403 FORBIDDEN]. Every write runs in one ``with_tenant(get_context())``
transaction under the tenant's role lock (shared with ``RoleService``), so a membership change
and a role assignment never interleave.

Rules (error codes in brackets):

- a team's name is unique per project, case-insensitively, among live teams; tenant-level teams
  share one bucket [409 TEAM_NAME_TAKEN];
- a project team's project must be live and visible [404 PROJECT_NOT_FOUND]; an organisation must
  be in the tenant [404 ORGANISATION_NOT_FOUND];
- members must be users of the tenant [404 USER_NOT_FOUND] and active [422 USER_INACTIVE];
- changing the members of a team that holds a privileged role, or deleting it, needs a stepped-up
  tenant_admin, as assigning that role would [403 TENANT_ADMIN_REQUIRED / STEP_UP_REQUIRED].

Membership changes emit ``team.membership_changed`` (only the users whose membership changed);
deleting a team removes its members and role assignments first. Team rows of another tenant are
invisible under RLS and come back as 404 [TEAM_NOT_FOUND].

``revoke_user_access`` is the ``user.deactivated`` handler: it soft-deletes the user's memberships
and direct role assignments on the dispatcher's connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.changes import record_grants_changed, record_membership_changed
from aip.modules.access.events import (
    ROLE_ASSIGNMENT_REMOVED,
    ROLE_ASSIGNMENT_VERSION,
    TEAM_CHANGED,
)
from aip.modules.access.roles import repository as roles_repo
from aip.modules.access.roles.service import (
    locked_tx,
    require_stepped_up_admin,
)
from aip.modules.access.teams import repository as repo
from aip.modules.access.teams.schemas import (
    MembersAdd,
    TeamCreate,
    TeamMemberOut,
    TeamOut,
    TeamUpdate,
)
from aip.modules.identity.api import get_user
from aip.modules.projects.api import ProjectsApi
from aip.platform.access import AccessPrincipal, Forbidden, PolicyService, Resource
from aip.platform.context import get_context, new_request_id
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = ["TEAM_MANAGE", "TeamService", "revoke_user_access"]

TEAM_MANAGE: Final = "access.team.manage"
_UNIQUE_VIOLATION: Final = "23505"
_FK_VIOLATION: Final = "23503"


@asynccontextmanager
async def _integrity() -> AsyncIterator[None]:
    try:
        yield
    except IntegrityError as exc:
        state = getattr(exc.orig, "sqlstate", None)
        if state == _UNIQUE_VIOLATION:
            raise DomainError(409, "TEAM_NAME_TAKEN") from None
        if state == _FK_VIOLATION:
            raise DomainError(404, "ORGANISATION_NOT_FOUND") from None
        raise


def _team_out(row: dict[str, Any]) -> TeamOut:
    return TeamOut.model_validate(row)


async def _team_event(conn: AsyncConnection, row: dict[str, Any], action: str) -> None:
    payload = {
        "teamId": row["id"],
        "action": action,
        "name": row["name"],
        "teamType": row["team_type"],
        "projectId": row["project_id"],
    }
    await emit(conn, TEAM_CHANGED, 1, Aggregate("team", row["id"]), payload)


class TeamService:
    def __init__(self, policy: PolicyService) -> None:
        self._policy = policy

    async def _check(self, actor: AccessPrincipal, project_id: UUID | None) -> None:
        resource = None if project_id is None else Resource(project_id=project_id)
        await self._policy.assert_can(actor, TEAM_MANAGE, resource)

    async def _authorise(self, team_id: UUID, actor: AccessPrincipal) -> None:
        # The policy reads grants on its own connection, so check before taking the write
        # transaction (never two connections per request at once).
        async with with_tenant(get_context()) as conn:
            team = await repo.get_team(conn, team_id)
        if team is None:
            raise DomainError(404, "TEAM_NOT_FOUND")
        await self._check(actor, team["project_id"])

    @staticmethod
    async def _locked_team(conn: AsyncConnection, team_id: UUID) -> dict[str, Any]:
        team = await repo.get_team(conn, team_id, for_update=True)
        if team is None:  # deleted since _authorise
            raise DomainError(404, "TEAM_NOT_FOUND")
        return team

    async def _gate_privileged(
        self, conn: AsyncConnection, team_id: UUID, actor: AccessPrincipal
    ) -> None:
        await require_stepped_up_admin(conn, actor, await repo.team_role_permissions(conn, team_id))

    async def list(self, actor: AccessPrincipal, *, project_id: UUID | None) -> list[TeamOut]:
        async with with_tenant(get_context()) as conn:
            rows = await repo.list_teams(conn, project_id=project_id)
        if (await self._policy.can(actor, TEAM_MANAGE)).allowed:
            return [_team_out(row) for row in rows]
        project_rows = [row for row in rows if row["project_id"] is not None]
        allowed = await self._policy.filter_allowed(
            actor, TEAM_MANAGE, project_rows, lambda row: Resource(project_id=row["project_id"])
        )
        if not allowed and project_id is not None:
            raise Forbidden(TEAM_MANAGE)
        return [_team_out(row) for row in allowed]

    async def create(self, body: TeamCreate, actor: AccessPrincipal) -> TeamOut:
        await self._check(actor, body.project_id)
        team_id = UUID(new_request_id())
        async with locked_tx() as conn:
            if body.project_id is not None and (
                await ProjectsApi().get_project(conn, body.project_id) is None
            ):
                raise DomainError(404, "PROJECT_NOT_FOUND")
            async with _integrity():
                await repo.insert_team(
                    conn,
                    team_id=team_id,
                    name=body.name,
                    team_type=body.team_type,
                    project_id=body.project_id,
                    organisation_id=body.organisation_id,
                    created_by=actor.actor_id if actor.kind == "user" else None,
                )
            row = await repo.get_team(conn, team_id)
            assert row is not None
            await _team_event(conn, row, "created")
        return _team_out(row)

    async def update(self, team_id: UUID, body: TeamUpdate, actor: AccessPrincipal) -> TeamOut:
        await self._authorise(team_id, actor)
        async with locked_tx() as conn:
            team = await self._locked_team(conn, team_id)
            fields: dict[str, Any] = {}
            if body.name is not None and body.name != team["name"]:
                fields["name"] = body.name
            if body.team_type is not None and body.team_type != team["team_type"]:
                fields["team_type"] = body.team_type
            if "organisation_id" in body.model_fields_set:
                fields["organisation_id"] = body.organisation_id
            if fields:
                async with _integrity():
                    await repo.update_team(conn, team_id, fields)
            row = await repo.get_team(conn, team_id)
            assert row is not None
            if fields:
                await _team_event(conn, row, "updated")
        return _team_out(row)

    async def delete(self, team_id: UUID, actor: AccessPrincipal) -> None:
        await self._authorise(team_id, actor)
        async with locked_tx() as conn:
            team = await self._locked_team(conn, team_id)
            await self._gate_privileged(conn, team_id, actor)
            for assignment_id in await repo.team_assignments(conn, team_id):
                row = await roles_repo.get_assignment(conn, assignment_id)
                assert row is not None
                await roles_repo.soft_delete_assignment(conn, assignment_id)
                await _assignment_removed(conn, row)
            removed = await repo.remove_all_members(conn, team_id)
            await repo.soft_delete_team(conn, team_id)
            await _team_event(conn, team, "deleted")
            await record_membership_changed(conn, team_id, removed, "removed")

    async def list_members(self, team_id: UUID, actor: AccessPrincipal) -> list[TeamMemberOut]:
        await self._authorise(team_id, actor)
        async with with_tenant(get_context()) as conn:
            rows = await repo.list_members(conn, team_id)
        return [TeamMemberOut.model_validate(row) for row in rows]

    async def add_members(
        self, team_id: UUID, body: MembersAdd, actor: AccessPrincipal
    ) -> list[TeamMemberOut]:
        await self._authorise(team_id, actor)
        async with locked_tx() as conn:
            await self._locked_team(conn, team_id)
            for user_id in sorted(set(body.user_ids)):
                user = await get_user(conn, user_id)
                if user is None:
                    raise DomainError(404, "USER_NOT_FOUND", userId=str(user_id))
                if user.status != "active":
                    raise DomainError(422, "USER_INACTIVE", field="userIds", userId=str(user_id))
            await self._gate_privileged(conn, team_id, actor)
            added = await repo.add_members(
                conn, team_id, body.user_ids, actor.actor_id if actor.kind == "user" else None
            )
            await record_membership_changed(conn, team_id, added, "added")
            rows = await repo.list_members(conn, team_id)
        return [TeamMemberOut.model_validate(row) for row in rows]

    async def remove_member(self, team_id: UUID, user_id: UUID, actor: AccessPrincipal) -> None:
        await self._authorise(team_id, actor)
        async with locked_tx() as conn:
            await self._locked_team(conn, team_id)
            await self._gate_privileged(conn, team_id, actor)
            if not await repo.remove_member(conn, team_id, user_id):
                raise DomainError(404, "MEMBER_NOT_FOUND")
            await record_membership_changed(conn, team_id, [user_id], "removed")


async def _assignment_removed(conn: AsyncConnection, row: dict[str, Any]) -> None:
    payload = {
        "assignmentId": row["id"],
        "userId": row["user_id"],
        "teamId": row["team_id"],
        "roleId": row["role_id"],
        "roleCode": row["role_code"],
        "scopeType": row["scope_type"],
        "projectId": row["project_id"],
        "validTo": row["valid_to"],
        "approvedBy": row["approved_by"],
    }
    await emit(
        conn,
        ROLE_ASSIGNMENT_REMOVED,
        ROLE_ASSIGNMENT_VERSION,
        Aggregate("role_assignment", row["id"]),
        payload,
    )


async def revoke_user_access(conn: AsyncConnection, user_id: UUID) -> None:
    """Soft-delete the user's team memberships and direct role assignments (``user.deactivated``).

    Runs on the caller's ``with_tenant`` connection (the dispatcher's), under the role lock.
    Idempotent: a second run finds nothing live and emits nothing.
    """
    await roles_repo.lock_tenant_roles(conn)
    for team_id in await repo.remove_user_memberships(conn, user_id):
        await record_membership_changed(conn, team_id, [user_id], "removed")
    assignments = await roles_repo.live_user_assignments(conn, user_id)
    for row in assignments:
        await roles_repo.soft_delete_assignment(conn, row["id"])
        await _assignment_removed(conn, row)
    if assignments:
        await record_grants_changed(conn, [user_id])
