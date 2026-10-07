"""Request context: tenant, project, actor and asset scope for the current work (ARCH-04)."""

from aip.platform.context.context import (
    ContextMissingError,
    RequestContext,
    get_context,
    run_with_context,
    use_context,
)
from aip.platform.context.middleware import RequestContextMiddleware
from aip.platform.context.resolvers import (
    DenyAllMembershipResolver,
    DenyAllPrincipalResolver,
    Principal,
    PrincipalResolver,
    ProjectMembershipResolver,
)

__all__ = [
    "ContextMissingError",
    "DenyAllMembershipResolver",
    "DenyAllPrincipalResolver",
    "Principal",
    "PrincipalResolver",
    "ProjectMembershipResolver",
    "RequestContext",
    "RequestContextMiddleware",
    "get_context",
    "run_with_context",
    "use_context",
]
