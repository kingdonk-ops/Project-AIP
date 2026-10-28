"""Authorisation runtime (ACCESS-01): permission catalogue, ``PolicyService``, route access.

Deny by default: every route declares ``public()``, ``authenticated()`` or ``requires(code)``,
and every permission check goes through ``PolicyService.can``. Platform code only; the
``permission`` table, its sync and the abilities route live in ``aip.modules.access``.
"""

from aip.platform.access.catalogue import (
    Catalogue,
    CatalogueError,
    PermissionDef,
    build_catalogue,
    load_manifests,
)
from aip.platform.access.dependencies import (
    AccessCheckedRoute,
    AccessDeclaration,
    PrincipalSource,
    TenantGuard,
    access_declarations,
    authenticated,
    current_principal,
    public,
    requires,
)
from aip.platform.access.grants import (
    AssetSubtreeScope,
    Grant,
    GrantProvider,
    GrantScope,
    ProjectScope,
    TenantScope,
)
from aip.platform.access.policy import (
    AccessPrincipal,
    Decision,
    DecisionReason,
    Forbidden,
    PolicyService,
    Resource,
)
from aip.platform.access.route_check import (
    RouteAccessError,
    check_routes,
    enforce_routes,
    install_access,
)

__all__ = [
    "AccessCheckedRoute",
    "AccessDeclaration",
    "AccessPrincipal",
    "AssetSubtreeScope",
    "Catalogue",
    "CatalogueError",
    "Decision",
    "DecisionReason",
    "Forbidden",
    "Grant",
    "GrantProvider",
    "GrantScope",
    "PermissionDef",
    "PolicyService",
    "PrincipalSource",
    "ProjectScope",
    "Resource",
    "RouteAccessError",
    "TenantGuard",
    "TenantScope",
    "access_declarations",
    "authenticated",
    "build_catalogue",
    "check_routes",
    "current_principal",
    "enforce_routes",
    "install_access",
    "load_manifests",
    "public",
    "requires",
]
