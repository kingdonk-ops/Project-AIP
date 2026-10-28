"""``RoleGrantProvider``: role assignments as ``PolicyService`` grants (ACCESS-02, ACCESS-04).

An assignment grants while it is live (not soft-deleted), has started (``valid_from <= now()``),
has not expired (``valid_to`` null or in the future), its role is live and the user is active.
A tenant-scope assignment gives ``TenantScope`` grants of the role's permissions; a project-scope
one gives ``ProjectScope(project_id)`` grants. A team assignment (ACCESS-04) grants through the
user's live memberships of live teams: the team's project scope, or the tenant scope when the team
has no project. Asset-subtree scopes give nothing until their task adds them. An operator-only
``platform.*`` code is never granted, even if a row holds one (review 11 L1; the
``role_permission`` CHECK and ``RoleService`` also refuse them). ``resolve_grants`` is that rule
as a pure function.

The read runs in its own ``with_tenant`` transaction for the principal's tenant, so RLS limits it
to that tenant. Without ``DATABASE_URL`` it grants nothing. Resolved grants are cached across
requests by ``policy_cache`` (ACCESS-04, ADR 0039), keyed by the user's and the tenant's cache
versions; the versions are read before Postgres, so an entry never holds rows older than its key.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from aip.modules.access.policy_cache import GrantRow, PolicyCache, get_policy_cache
from aip.modules.access.roles import repository as repo
from aip.modules.access.roles.default_roles import OPERATOR_ONLY_PREFIX
from aip.platform.access import AccessPrincipal, Grant, ProjectScope, TenantScope
from aip.platform.db.engine import DATABASE_URL_ENV
from aip.platform.db.session import with_tenant

__all__ = ["AssignmentGrant", "RoleGrantProvider", "resolve_grants"]


@dataclass(frozen=True, slots=True)
class AssignmentGrant:
    """One permission from one active assignment, before scoping."""

    permission: str
    scope_type: str
    project_id: UUID | None = None
    team_id: UUID | None = None


def resolve_grants(
    assignments: Iterable[AssignmentGrant], teams: Mapping[UUID, UUID | None]
) -> list[GrantRow]:
    """The grants ``assignments`` give a user who is a live member of ``teams``.

    ``teams`` maps each such team to its project (``None``: a tenant-level team). A team
    assignment of a team the user is not in gives nothing; an unknown scope gives nothing.
    """
    rows: set[GrantRow] = set()
    for a in assignments:
        if a.permission.startswith(OPERATOR_ONLY_PREFIX):
            continue
        if a.scope_type == "tenant":
            rows.add((a.permission, "tenant", None))
        elif a.scope_type == "project" and a.project_id is not None:
            rows.add((a.permission, "project", str(a.project_id)))
        elif a.scope_type == "team" and a.team_id is not None and a.team_id in teams:
            project = teams[a.team_id]
            if project is None:
                rows.add((a.permission, "tenant", None))
            else:
                rows.add((a.permission, "project", str(project)))
    return sorted(rows, key=lambda r: (r[0], r[1], r[2] or ""))


def _as_grants(rows: Sequence[GrantRow]) -> list[Grant]:
    grants: list[Grant] = []
    for permission, scope, project in rows:
        if scope == "tenant":
            grants.append(Grant(permission, TenantScope()))
        elif scope == "project" and project is not None:
            grants.append(Grant(permission, ProjectScope(UUID(project))))
    return grants


class RoleGrantProvider:
    def __init__(self, cache: PolicyCache | None = None) -> None:
        self._cache = cache  # None: the process cache from REDIS_URL

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        if principal.kind != "user" or principal.actor_id is None:
            return []
        if not os.environ.get(DATABASE_URL_ENV):  # no database (unit tests): no role grants
            return []
        tenant_id, user_id = principal.tenant_id, principal.actor_id
        cache = self._cache or get_policy_cache()
        versions = await cache.versions(tenant_id, user_id)
        if versions is not None:
            cached = await cache.get(tenant_id, user_id, versions)
            if cached is not None:
                return _as_grants(cached)
        async with with_tenant(tenant_id) as conn:
            assignments = [AssignmentGrant(*row) for row in await repo.active_grants(conn, user_id)]
            teams = await repo.member_teams(conn, user_id)
        rows = resolve_grants(assignments, teams)
        if versions is not None:
            await cache.put(tenant_id, user_id, versions, rows)
        return _as_grants(rows)
