"""``PortalGrantProvider``: portal grants as ``PolicyService`` grants (PORTAL-01).

The only source of a portal user's permissions. ``serves_external = True``, so the policy service
asks it for external principals (``AccessPrincipal.external``, a ``user_class = 'portal'``
session) and never for internal ones, and asks no other provider for a portal user.

It gives nothing unless the caller's ``portal_users`` row is ``active`` (after the first sign-in,
not suspended) and identity's ``get_user`` says the account is ``active`` and of class ``portal``.
Then each live grant (not revoked, not soft-deleted, ``expires_at`` in the future: ``grant_state``,
so expiry needs no job) gives, for each of its actions, the codes of ``ACTION_PERMISSIONS[action]``
at ``ProjectScope(project_id)``, or ``AssetSubtreeScope(project_id, asset_id)`` for a subtree
grant. The read runs in its own ``with_tenant`` transaction for the principal's tenant. Without
``DATABASE_URL`` it grants nothing, as ``RoleGrantProvider`` does.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import ClassVar

from aip.modules.identity import api as identity
from aip.modules.portal import policies
from aip.modules.portal import repository as repo
from aip.platform.access import AccessPrincipal, AssetSubtreeScope, Grant, GrantScope, ProjectScope
from aip.platform.db.engine import DATABASE_URL_ENV
from aip.platform.db.session import with_tenant

__all__ = ["PortalGrantProvider"]


class PortalGrantProvider:
    serves_external: ClassVar[bool] = True

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        if not principal.external or principal.kind != "user" or principal.actor_id is None:
            return []
        if not os.environ.get(DATABASE_URL_ENV):  # no database (unit tests): no portal grants
            return []
        async with with_tenant(principal.tenant_id) as conn:
            portal_user = await repo.get_user_by_user_id(conn, principal.actor_id)
            if portal_user is None or portal_user["status"] != "active":
                return []
            user = await identity.get_user(conn, principal.actor_id)
            if user is None or user.status != "active" or user.user_class != "portal":
                return []
            rows = await repo.unrevoked_grants(conn, [portal_user["id"]])
        now = datetime.now(UTC)
        grants: list[Grant] = []
        for row in rows:
            if policies.grant_state(row, now) != "live":
                continue
            scope: GrantScope = (
                ProjectScope(row["project_id"])
                if row["asset_id"] is None
                else AssetSubtreeScope(row["project_id"], row["asset_id"])
            )
            grants.extend(
                Grant(code, scope) for code in sorted(policies.expand_actions(row["actions"]))
            )
        return grants
