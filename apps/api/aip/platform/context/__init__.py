"""Request context: tenant, project, actor and asset scope for the current work (ARCH-04)."""

from aip.platform.context.context import (
    SAFE_REQUEST_ID,
    ContextMissingError,
    RequestContext,
    current_request_id,
    get_context,
    new_request_id,
    reset_request_id,
    run_with_context,
    set_request_id,
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
    "SAFE_REQUEST_ID",
    "ContextMissingError",
    "DenyAllMembershipResolver",
    "DenyAllPrincipalResolver",
    "Principal",
    "PrincipalResolver",
    "ProjectMembershipResolver",
    "RequestContext",
    "RequestContextMiddleware",
    "current_request_id",
    "get_context",
    "new_request_id",
    "reset_request_id",
    "run_with_context",
    "set_request_id",
    "use_context",
]
