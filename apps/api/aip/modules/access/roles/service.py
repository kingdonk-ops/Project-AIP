"""Roles and role assignments (ACCESS-02, ADR 0020).

Every change runs in one ``with_tenant(get_context())`` transaction that first takes the tenant's
role lock (``lock_tenant_roles``), then changes rows, emits its outbox event and bumps the tenant's
access version, so all of it commits or rolls back together and concurrent changes serialise.

Guards (error codes in brackets):

- system roles keep their code and name and cannot be deleted [409 SYSTEM_ROLE_IMMUTABLE]; their
  permissions may change, which stamps ``customised_at``; ``reset`` restores the defaults;
- a role with live assignments cannot be deleted [409 ROLE_IN_USE];
- a role's permissions must be live catalogue codes [422 UNKNOWN_PERMISSION], except that a
  deprecated code the role already holds may be kept (editors must never hide it);
- a role can never hold an operator-only ``platform.*`` code, even one it already holds
  [422 OPERATOR_ONLY_PERMISSION]: those act across tenants (ADR 0029, ENT-01);
- any change that touches a privileged permission needs an actor who is tenant_admin at tenant
  scope [403 TENANT_ADMIN_REQUIRED] with ``aal=2`` [403 STEP_UP_REQUIRED]: creating or cloning a
  role that holds one, changing the permissions or resetting a role that holds or would hold one,
  and assigning or removing such a role (``_require_stepped_up_admin``);
- the 11 system role codes are reserved [409 ROLE_CODE_TAKEN], and a role may be assigned only
  once per user and scope while the assignment is live [409 ASSIGNMENT_EXISTS];
- no change may leave the tenant without an active tenant_admin [409 LAST_TENANT_ADMIN] or without
  anyone holding ``access.role.manage`` at tenant scope [409 LAST_ROLE_MANAGER].

Rows of another tenant are invisible under RLS and come back as 404.

ACCESS-04: a role may be assigned to a team (``scope.type == "team"``; 404 TEAM_NOT_FOUND, one
live assignment per team and role). Every change that can alter someone's grants records it
(``changes.record_grants_changed``: the ``access.grants_changed`` event, the access version and
the after-commit policy cache bump); assignment events are emitted at v2 (with ``teamId``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.changes import record_grants_changed
from aip.modules.access.events import (
    ROLE_ASSIGNMENT_CREATED,
    ROLE_ASSIGNMENT_REMOVED,
    ROLE_ASSIGNMENT_VERSION,
    ROLE_CHANGED,
)
from aip.modules.access.repository import bump_access_version
from aip.modules.access.roles import repository as repo
from aip.modules.access.roles.default_roles import OPERATOR_ONLY_PREFIX, ROLE_CODES
from aip.modules.access.roles.schemas import (
    AssignmentCreate,
    AssignmentOut,
    RoleClone,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)
from aip.modules.access.roles.seed import default_role_permissions
from aip.modules.access.teams import repository as teams_repo
from aip.modules.identity.api import ensure_invited_sso_user, get_user
from aip.modules.projects.api import ProjectsApi
from aip.platform.access import AccessPrincipal
from aip.platform.context import get_context, new_request_id
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "AssignmentService",
    "RoleService",
    "bootstrap_tenant_admin",
    "locked_tx",
    "require_stepped_up_admin",
]

TENANT_ADMIN: Final = "tenant_admin"
ROLE_MANAGE: Final = "access.role.manage"
_UNIQUE_VIOLATION: Final = "23505"


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


@asynccontextmanager
async def _locked_tx() -> AsyncIterator[AsyncConnection]:
    async with _tx() as conn:
        await repo.lock_tenant_roles(conn)
        yield conn


locked_tx = _locked_tx  # the teams service shares the tenant's role lock (ACCESS-04)


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


@asynccontextmanager
async def _unique(code: str) -> AsyncIterator[None]:
    try:
        yield
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION:
            raise DomainError(409, code) from None
        raise


@dataclass(frozen=True, slots=True)
class _Lockout:
    """Who can still administer the tenant, counted before a change and checked after it."""

    admins: int
    managers: int

    @classmethod
    async def count(cls, conn: AsyncConnection) -> _Lockout:
        return cls(
            admins=await repo.count_holders(conn, role_code=TENANT_ADMIN),
            managers=await repo.count_holders(conn, permission=ROLE_MANAGE),
        )

    async def check(self, conn: AsyncConnection) -> None:
        after = await _Lockout.count(conn)
        if self.admins > 0 and after.admins == 0:
            raise DomainError(409, "LAST_TENANT_ADMIN")
        if self.managers > 0 and after.managers == 0:
            raise DomainError(409, "LAST_ROLE_MANAGER")


async def _require_stepped_up_admin(
    conn: AsyncConnection, actor: AccessPrincipal, permissions: Iterable[str]
) -> bool:
    """Gate a change touching ``permissions``; True when one of them is privileged.

    Privileged changes need a user who is tenant_admin at tenant scope, stepped up to ``aal=2``.
    """
    if not set(permissions) & await repo.privileged_codes(conn):
        return False
    if (
        actor.kind != "user"
        or actor.actor_id is None
        or not await repo.holds_role_at_tenant(conn, actor.actor_id, TENANT_ADMIN)
    ):
        raise DomainError(403, "TENANT_ADMIN_REQUIRED")
    if actor.aal < 2:
        raise DomainError(403, "STEP_UP_REQUIRED")
    return True


require_stepped_up_admin = _require_stepped_up_admin  # teams gate privileged memberships too


def _check_code(code: str) -> None:
    if code in ROLE_CODES:
        raise DomainError(409, "ROLE_CODE_TAKEN")


def _role_out(row: dict[str, Any]) -> RoleOut:
    return RoleOut.model_validate({**row, "permissions": list(row["permissions"])})


async def _role_or_404(conn: AsyncConnection, role_id: UUID) -> dict[str, Any]:
    role = await repo.get_role(conn, role_id, for_update=True)
    if role is None:
        raise DomainError(404, "ROLE_NOT_FOUND")
    return role


async def _live_codes(conn: AsyncConnection) -> set[str]:
    return {code for code, _, _ in await repo.live_catalogue(conn)}


async def _checked_permissions(
    conn: AsyncConnection, codes: Iterable[str], *, already_held: Iterable[str] = ()
) -> set[str]:
    """``codes`` as a set; each must be a live catalogue code or one the role already holds."""
    wanted = set(codes)
    if operator_only := sorted(c for c in wanted if c.startswith(OPERATOR_ONLY_PREFIX)):
        raise DomainError(
            422, "OPERATOR_ONLY_PERMISSION", field="permissions", permissions=operator_only
        )
    allowed = await _live_codes(conn) | set(already_held)
    if unknown := sorted(wanted - allowed):
        raise DomainError(422, "UNKNOWN_PERMISSION", field="permissions", permissions=unknown)
    return wanted


async def _role_event(
    conn: AsyncConnection,
    role_id: UUID,
    code: str,
    action: str,
    before: Iterable[str] | None,
    after: Iterable[str] | None,
) -> None:
    payload = {
        "roleId": role_id,
        "code": code,
        "action": action,
        "before": None if before is None else sorted(before),
        "after": None if after is None else sorted(after),
    }
    await emit(conn, ROLE_CHANGED, 1, Aggregate("role", role_id), payload)


class RoleService:
    async def list(self) -> list[RoleOut]:
        async with _tx() as conn:
            return [_role_out(row) for row in await repo.list_roles(conn)]

    async def create(self, body: RoleCreate, actor: AccessPrincipal) -> RoleOut:
        _check_code(body.code)
        async with _locked_tx() as conn:
            permissions = await _checked_permissions(conn, body.permissions)
            await _require_stepped_up_admin(conn, actor, permissions)
            role_id = await self._insert_custom(conn, body.code, body.name, permissions)
            await _role_event(conn, role_id, body.code, "created", None, permissions)
            await bump_access_version(conn)
            return _role_out(await _role_or_404(conn, role_id))

    async def clone(self, role_id: UUID, body: RoleClone, actor: AccessPrincipal) -> RoleOut:
        _check_code(body.code)
        async with _locked_tx() as conn:
            source = await _role_or_404(conn, role_id)
            permissions = set(source["permissions"])
            await _require_stepped_up_admin(conn, actor, permissions)
            new_id = await self._insert_custom(conn, body.code, body.name, permissions)
            await _role_event(conn, new_id, body.code, "created", None, permissions)
            await bump_access_version(conn)
            return _role_out(await _role_or_404(conn, new_id))

    async def update(self, role_id: UUID, body: RoleUpdate, actor: AccessPrincipal) -> RoleOut:
        async with _locked_tx() as conn:
            role = await _role_or_404(conn, role_id)
            if role["is_system"] and (
                (body.code is not None and body.code != role["code"]) or body.name is not None
            ):
                raise DomainError(409, "SYSTEM_ROLE_IMMUTABLE")
            if not role["is_system"] and body.code is not None and body.code != role["code"]:
                _check_code(body.code)
            before = set(role["permissions"])
            lockout = await _Lockout.count(conn)
            after = before
            if body.permissions is not None:
                after = await _checked_permissions(conn, body.permissions, already_held=before)
                # Deprecated codes the role holds are never dropped by an edit (ACCESS-01).
                after |= before - await _live_codes(conn)
            changed = after != before
            if changed:
                await _require_stepped_up_admin(conn, actor, before | after)
                await repo.set_role_permissions(conn, role_id, after)
            renamed = not role["is_system"] and (
                (body.code is not None and body.code != role["code"])
                or (body.name is not None and body.name != role["name"])
            )
            if changed or renamed:
                async with _unique("ROLE_CODE_TAKEN"):
                    await repo.update_role(
                        conn,
                        role_id,
                        code=None if role["is_system"] else body.code,
                        name=None if role["is_system"] else body.name,
                        customised=True if (changed and role["is_system"]) else None,
                    )
                await lockout.check(conn)
                code = role["code"] if role["is_system"] or body.code is None else body.code
                await _role_event(conn, role_id, code, "updated", before, after)
                if changed:
                    await record_grants_changed(conn, None)  # every holder, tenant-wide
                else:
                    await bump_access_version(conn)
            return _role_out(await _role_or_404(conn, role_id))

    async def delete(self, role_id: UUID) -> None:
        async with _locked_tx() as conn:
            role = await _role_or_404(conn, role_id)
            if role["is_system"]:
                raise DomainError(409, "SYSTEM_ROLE_IMMUTABLE")
            if await repo.role_in_use(conn, role_id):
                raise DomainError(409, "ROLE_IN_USE")
            await repo.soft_delete_role(conn, role_id)
            await _role_event(conn, role_id, role["code"], "deleted", role["permissions"], None)
            await bump_access_version(conn)

    async def reset(self, role_id: UUID, actor: AccessPrincipal) -> RoleOut:
        """Restore a system role's shipped permissions and clear ``customised_at``."""
        async with _locked_tx() as conn:
            role = await _role_or_404(conn, role_id)
            if not role["is_system"]:
                raise DomainError(409, "NOT_A_SYSTEM_ROLE")
            before = set(role["permissions"])
            lockout = await _Lockout.count(conn)
            defaults = set((await default_role_permissions(conn)).get(role["code"], frozenset()))
            keep = before - await _live_codes(conn)  # deprecated codes stay
            after = defaults | keep
            await _require_stepped_up_admin(conn, actor, before | after)
            await repo.set_role_permissions(conn, role_id, defaults, keep=keep)
            await repo.update_role(conn, role_id, customised=False)
            if after != before or role["customised_at"] is not None:
                await lockout.check(conn)
                await _role_event(conn, role_id, role["code"], "reset", before, after)
                if after != before:
                    await record_grants_changed(conn, None)
                else:
                    await bump_access_version(conn)
            return _role_out(await _role_or_404(conn, role_id))

    @staticmethod
    async def _insert_custom(
        conn: AsyncConnection, code: str, name: str, permissions: set[str]
    ) -> UUID:
        role_id = _new_id()
        async with _unique("ROLE_CODE_TAKEN"):
            await repo.insert_role(
                conn, role_id=role_id, code=code, name=name, name_term_key=None, is_system=False
            )
        await repo.set_role_permissions(conn, role_id, permissions)
        return role_id


async def bootstrap_tenant_admin(
    conn: AsyncConnection, *, tenant_id: UUID, email: str, idp_alias: str
) -> bool:
    """Dev and demo only (TESTING-09): make ``email`` a tenant-scope ``tenant_admin``.

    Nobody holds a role after a JIT sign-in, and every role change needs a stepped-up tenant
    admin, so the first admin of a fixture tenant is seeded here: an invited SSO user (linked on
    their first sign-in) plus the assignment, emitted like any other. Runs on the caller's
    ``with_tenant`` connection inside a request context. Idempotent; ``True`` when it assigned.
    ``LookupError`` when the tenant has no ``tenant_admin`` role (run ``seed-roles`` first).
    """
    await repo.lock_tenant_roles(conn)
    role = await repo.get_role_by_code(conn, TENANT_ADMIN)
    if role is None:
        raise LookupError("tenant_admin role missing: run `aip-access seed-roles` first")
    user_id = await ensure_invited_sso_user(
        conn, tenant_id=tenant_id, email=email, idp_alias=idp_alias
    )
    if await repo.has_live_tenant_assignment(conn, user_id, role["id"]):
        return False
    assignment_id = _new_id()
    await repo.insert_assignment(
        conn,
        assignment_id=assignment_id,
        user_id=user_id,
        role_id=role["id"],
        scope_type="tenant",
        project_id=None,
        valid_to=None,
        approved_by=None,
        created_by=None,
    )
    row = await repo.get_assignment(conn, assignment_id)
    assert row is not None
    await emit(
        conn,
        ROLE_ASSIGNMENT_CREATED,
        ROLE_ASSIGNMENT_VERSION,
        Aggregate("role_assignment", assignment_id),
        _assignment_payload(row),
    )
    await record_grants_changed(conn, [user_id])
    return True


def _assignment_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
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


async def _holders(conn: AsyncConnection, row: dict[str, Any]) -> list[UUID]:
    """The users an assignment row gives grants to: its user, or its team's live members."""
    if row["team_id"] is not None:
        return await teams_repo.member_ids(conn, row["team_id"])
    return [row["user_id"]]


class AssignmentService:
    async def list(
        self, *, user_id: UUID | None, project_id: UUID | None, team_id: UUID | None = None
    ) -> list[AssignmentOut]:
        async with _tx() as conn:
            rows = await repo.list_assignments(
                conn, user_id=user_id, project_id=project_id, team_id=team_id
            )
        return [AssignmentOut.model_validate(row) for row in rows]

    async def create(self, body: AssignmentCreate, actor: AccessPrincipal) -> AssignmentOut:
        if actor.kind != "user" or actor.actor_id is None:
            raise DomainError(403, "TENANT_ADMIN_REQUIRED")  # only people assign roles
        scope = body.scope
        if scope.type not in ("tenant", "project", "team"):
            raise DomainError(400, "SCOPE_NOT_SUPPORTED")
        if body.valid_to is not None and body.valid_to <= datetime.now(UTC):
            raise DomainError(422, "INVALID_VALID_TO", field="validTo")
        async with _locked_tx() as conn:
            if body.user_id is not None:
                user = await get_user(conn, body.user_id)
                if user is None:
                    raise DomainError(404, "USER_NOT_FOUND")
                if user.status != "active":
                    raise DomainError(422, "USER_INACTIVE", field="userId")
            if scope.team_id is not None and await teams_repo.get_team(conn, scope.team_id) is None:
                raise DomainError(404, "TEAM_NOT_FOUND")
            role = await repo.get_role(conn, body.role_id)
            if role is None:
                raise DomainError(404, "ROLE_NOT_FOUND")
            if scope.project_id is not None and (
                await ProjectsApi().get_project(conn, scope.project_id) is None
            ):
                raise DomainError(404, "PROJECT_NOT_FOUND")
            privileged = await _require_stepped_up_admin(conn, actor, role["permissions"])
            approved_by = actor.actor_id if privileged else None
            assignment_id = _new_id()
            async with _unique("ASSIGNMENT_EXISTS"):
                await repo.insert_assignment(
                    conn,
                    assignment_id=assignment_id,
                    user_id=body.user_id,
                    role_id=body.role_id,
                    scope_type=scope.type,
                    project_id=scope.project_id,
                    valid_to=body.valid_to,
                    approved_by=approved_by,
                    created_by=actor.actor_id,
                    team_id=scope.team_id,
                )
            row = await repo.get_assignment(conn, assignment_id)
            assert row is not None
            await emit(
                conn,
                ROLE_ASSIGNMENT_CREATED,
                ROLE_ASSIGNMENT_VERSION,
                Aggregate("role_assignment", assignment_id),
                _assignment_payload(row),
            )
            await record_grants_changed(conn, await _holders(conn, row))
        return AssignmentOut.model_validate(row)

    async def delete(self, assignment_id: UUID, actor: AccessPrincipal) -> None:
        async with _locked_tx() as conn:
            row = await repo.get_assignment(conn, assignment_id)
            if row is None:
                raise DomainError(404, "ASSIGNMENT_NOT_FOUND")
            await _require_stepped_up_admin(
                conn, actor, await repo.role_permissions(conn, row["role_id"])
            )
            lockout = await _Lockout.count(conn)
            await repo.soft_delete_assignment(conn, assignment_id)
            await lockout.check(conn)
            await emit(
                conn,
                ROLE_ASSIGNMENT_REMOVED,
                ROLE_ASSIGNMENT_VERSION,
                Aggregate("role_assignment", assignment_id),
                _assignment_payload(row),
            )
            await record_grants_changed(conn, await _holders(conn, row))
