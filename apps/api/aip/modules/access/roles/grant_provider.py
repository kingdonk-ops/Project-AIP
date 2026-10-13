"""``RoleGrantProvider``: role assignments as ``PolicyService`` grants (ACCESS-02).

An assignment grants while it is live (not soft-deleted), has started (``valid_from <= now()``),
has not expired (``valid_to`` null or in the future), its role is live and its user is active.
A tenant-scope assignment gives ``TenantScope`` grants of the role's permissions; a project-scope
one gives ``ProjectScope(project_id)`` grants. Team and asset-subtree scopes give nothing until
their tasks add them. The read runs in its own ``with_tenant`` transaction for the principal's
tenant, so RLS limits it to that tenant. Without ``DATABASE_URL`` it grants nothing.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from aip.modules.access.roles import repository as repo
from aip.platform.access import AccessPrincipal, Grant, ProjectScope, TenantScope
from aip.platform.db.engine import DATABASE_URL_ENV
from aip.platform.db.session import with_tenant

__all__ = ["RoleGrantProvider"]


class RoleGrantProvider:
    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        if principal.kind != "user" or principal.actor_id is None:
            return []
        if not os.environ.get(DATABASE_URL_ENV):  # no database (unit tests): no role grants
            return []
        async with with_tenant(principal.tenant_id) as conn:
            rows = await repo.active_grants(conn, principal.actor_id)
        grants: list[Grant] = []
        for permission, scope_type, project_id in rows:
            if scope_type == "tenant":
                grants.append(Grant(permission, TenantScope()))
            elif scope_type == "project" and project_id is not None:
                grants.append(Grant(permission, ProjectScope(project_id)))
        return grants
