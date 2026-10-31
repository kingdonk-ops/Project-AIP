"""Published interface of the access module.

Other modules may import only this file. Keep it small and stable.

- ``get_access_version`` / ``bump_access_version`` (ADR 0020): ACCESS-02 bumps the version in the
  same transaction as every role, override or assignment change; ACCESS-04 keys its grant cache
  by it. Both take the connection from ``with_tenant``.
- ``sync_catalogue``: the startup sync of the permission catalogue (called by ``aip.main``).
- ``seed_default_roles`` (ACCESS-02): the 11 system roles for the connection's tenant, idempotent
  (TENANCY-05 provisioning calls it). ``RoleGrantProvider``: role assignments as policy grants
  (registered by ``aip.main``).
- ``has_role(conn, user_id, role_code, project_id=None)`` (TENANCY-03): whether the user holds
  the role tenant-wide or on that project; takes the connection from ``with_tenant``.
- ``role_codes(conn, user_id, project_id=None)`` (APPROVALS-02): the codes of the roles the user
  actively holds tenant-wide or on that project, sorted (a transition guard's ``actor.roles``).
- ``role_code_for_id(conn, role_id)`` / ``get_team_ref(conn, team_id)`` (APPROVALS-04): resolve a
  route step's role or team approver; ``None`` for an unknown, deleted or other tenant's row.

- ``list_team_members(conn, team_id)`` / ``teams_for_user(conn, user_id)`` (ACCESS-04, for
  APPROVALS-04 team approvers): the active users with a live membership of a live team, sorted;
  and the live teams a user belongs to as ``TeamRef``s. Both take the ``with_tenant`` connection.
- ``configure_policy_cache`` (ACCESS-04): swap the process grant cache (tests, wiring).

The authorisation runtime itself (``PolicyService``, ``requires``) is ``aip.platform.access``.
"""

from __future__ import annotations

from typing import Protocol

from aip.modules.access.policy_cache import configure_policy_cache
from aip.modules.access.repository import (
    PermissionRow,
    bump_access_version,
    get_access_version,
    list_permissions,
)
from aip.modules.access.roles.grant_provider import RoleGrantProvider
from aip.modules.access.roles.repository import has_role, role_code_for_id, role_codes
from aip.modules.access.roles.seed import SeedReport, seed_default_roles
from aip.modules.access.service import sync_catalogue
from aip.modules.access.teams_api import TeamRef, get_team_ref, list_team_members, teams_for_user

# ACCESS-03: the project-scope helpers live in the DB-access layer (ADR 0002; aip.platform must not
# import aip.modules, ARCH-03). Re-exported here so other modules reach them via the access public
# interface. ``with_tenant(get_context())`` already binds a user principal for request handlers;
# use ``run_as_system`` in a worker job that must see every project-scoped row in a tenant.
from aip.platform.db.scope import ScopePrincipal, run_as_system, with_principal

__all__ = [
    "ModuleApi",
    "PermissionRow",
    "RoleGrantProvider",
    "ScopePrincipal",
    "SeedReport",
    "TeamRef",
    "bump_access_version",
    "configure_policy_cache",
    "get_access_version",
    "get_api",
    "get_team_ref",
    "has_role",
    "list_permissions",
    "list_team_members",
    "role_code_for_id",
    "role_codes",
    "run_as_system",
    "seed_default_roles",
    "sync_catalogue",
    "teams_for_user",
    "with_principal",
]


class ModuleApi(Protocol):
    """The operations access offers to other modules."""


def get_api() -> ModuleApi:
    """Return the access module's published interface."""
    raise NotImplementedError
