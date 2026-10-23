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

The authorisation runtime itself (``PolicyService``, ``requires``) is ``aip.platform.access``.
"""

from __future__ import annotations

from typing import Protocol

from aip.modules.access.repository import (
    PermissionRow,
    bump_access_version,
    get_access_version,
    list_permissions,
)
from aip.modules.access.roles.grant_provider import RoleGrantProvider
from aip.modules.access.roles.repository import has_role, role_codes
from aip.modules.access.roles.seed import SeedReport, seed_default_roles
from aip.modules.access.service import sync_catalogue

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
    "bump_access_version",
    "get_access_version",
    "get_api",
    "has_role",
    "list_permissions",
    "role_codes",
    "run_as_system",
    "seed_default_roles",
    "sync_catalogue",
    "with_principal",
]


class ModuleApi(Protocol):
    """The operations access offers to other modules."""


def get_api() -> ModuleApi:
    """Return the access module's published interface."""
    raise NotImplementedError
