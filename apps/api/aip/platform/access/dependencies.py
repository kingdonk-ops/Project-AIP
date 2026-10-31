"""Access declarations for routes (ACCESS-01): ``public()``, ``authenticated()``, ``requires()``.

Every route declares exactly how it is reached, as a route dependency::

    @router.get("/things", dependencies=[Depends(requires("things.thing.read"))])

- ``public()``: no session needed (sign-in, health, version).
- ``authenticated()``: a verified principal, no permission. Also usable as a parameter,
  ``principal: Annotated[AccessPrincipal, Depends(authenticated())]``.
- ``requires(code, resource=None)``: a principal that ``PolicyService.can`` allows ``code`` on
  ``resource(request)`` (sync or async; ``None`` checks tenant-wide grants only). Denied ->
  ``Forbidden`` -> 403 ``{"code": "FORBIDDEN", "permission": code}``. A resolver that loads a row
  outside RLS must set ``Resource.tenant_id``; ``None`` means the caller's own tenant.

Each declaration carries an access marker, which counts only as a top-level dependency (route,
router or endpoint parameter; never nested in a helper). ``AccessCheckedRoute`` answers 403 for a
route that, as mounted, carries none, and ``route_check.check_routes`` refuses to start with one.

The principal comes from ``app.state.access_principal_source`` when the app sets one (the identity
module's ``get_principal``, wired in ``aip.main``), otherwise from the ARCH-04 request context.
No principal -> 401 ``NOT_AUTHENTICATED``.

Every non-``public()`` route also checks the caller's tenant: when the app sets
``app.state.access_tenant_guard`` (tenancy's active-tenant check, wired in ``aip.main``), it runs
once per request right after the principal resolves and raises 401/403 for a tenant that may not
be served (TENANCY-01: a suspended tenant gets 403 on every tenant-scoped route).

PORTAL-02 (ADR 0036 choice 7): the routes an external principal (a portal user) may reach are an
allow-list. ``authenticated(external=True)`` and ``requires(code, external=True)`` accept **only**
external principals; every other non-``public()`` route refuses an external principal. Both
refusals are 404 ``{"code": "NOT_FOUND"}`` (``RouteHidden``), not 403, so neither audience can map
the other's API. ``route_check`` keeps external routes under ``EXTERNAL_PREFIXES``.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request
from fastapi import routing as fastapi_routing
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from aip.platform.access.policy import AccessPrincipal, Forbidden, PolicyService, Resource
from aip.platform.context import ContextMissingError, get_context

__all__ = [
    "ACCESS_MARKER",
    "AccessCheckedRoute",
    "AccessDeclaration",
    "PrincipalSource",
    "ResourceResolver",
    "RouteHidden",
    "TenantGuard",
    "access_declarations",
    "authenticated",
    "current_principal",
    "public",
    "requires",
]

ACCESS_MARKER = "__aip_access__"

AccessKind = Literal["public", "authenticated", "requires"]
PrincipalSource = Callable[[Request], Awaitable[AccessPrincipal | None]]
ResourceResolver = Callable[[Request], Resource | Awaitable[Resource | None] | None]
# Raises (HTTPException 401/403) when the principal's tenant may not be served; returns otherwise.
TenantGuard = Callable[[Request, AccessPrincipal], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AccessDeclaration:
    kind: AccessKind
    permission: str | None = None
    external: bool = False


class RouteHidden(Exception):
    """The route is not for this kind of principal (PORTAL-02): rendered as 404 ``NOT_FOUND``."""


def _not_authenticated() -> HTTPException:
    return HTTPException(
        status_code=401, detail={"code": "NOT_AUTHENTICATED", "message": "not authenticated"}
    )


async def current_principal(request: Request) -> AccessPrincipal:
    """The caller as an ``AccessPrincipal`` (resolved once per request), or 401."""
    cached: AccessPrincipal | None = getattr(request.state, "access_principal", None)
    if cached is not None:
        return cached
    source: PrincipalSource | None = getattr(request.app.state, "access_principal_source", None)
    principal: AccessPrincipal | None
    if source is not None:
        principal = await source(request)
    else:
        try:
            ctx = get_context()
        except ContextMissingError:
            principal = None
        else:
            # A tenant-only context (no actor) is not a caller the policy can reason about.
            principal = (
                None
                if ctx.actor_id is None
                else AccessPrincipal(tenant_id=ctx.tenant_id, actor_id=ctx.actor_id)
            )
    if principal is None:
        raise _not_authenticated()
    guard: TenantGuard | None = getattr(request.app.state, "access_tenant_guard", None)
    if guard is not None:
        await guard(request, principal)  # before caching: a refused caller is never cached
    request.state.access_principal = principal
    return principal


def policy_of(request: Request) -> PolicyService | None:
    return getattr(request.app.state, "access_policy", None)


class _Public:
    async def __call__(self) -> None:
        return None


async def _audience_principal(request: Request, external: bool) -> AccessPrincipal:
    """The caller, refused with ``RouteHidden`` unless its kind matches the route's (PORTAL-02)."""
    principal = await current_principal(request)
    if principal.external != external:
        raise RouteHidden
    return principal


class _Authenticated:
    def __init__(self, external: bool) -> None:
        self.external = external

    async def __call__(self, request: Request) -> AccessPrincipal:
        return await _audience_principal(request, self.external)


class _Requires:
    def __init__(self, code: str, resource: ResourceResolver | None, external: bool) -> None:
        self.code = code
        self.resource = resource
        self.external = external

    async def __call__(self, request: Request) -> AccessPrincipal:
        principal = await _audience_principal(request, self.external)
        policy = policy_of(request)
        if policy is None:  # access not installed on this app: deny
            raise Forbidden(self.code)
        resource: Resource | None = None
        if self.resource is not None:
            value = self.resource(request)
            resource = await value if inspect.isawaitable(value) else value
        await policy.assert_can(principal, self.code, resource)
        return principal


def _mark[T](dependency: T, declaration: AccessDeclaration) -> T:
    setattr(dependency, ACCESS_MARKER, declaration)
    return dependency


def public() -> Callable[[], Awaitable[None]]:
    """No session needed. Use only for sign-in, health and other deliberately open routes."""
    return _mark(_Public(), AccessDeclaration("public"))


def authenticated(external: bool = False) -> Callable[[Request], Awaitable[AccessPrincipal]]:
    """Any verified principal of the route's kind (internal, or external with ``external=True``);
    no permission is checked."""
    return _mark(
        _Authenticated(external), AccessDeclaration("authenticated", external=external)
    )


def requires(
    code: str, resource: ResourceResolver | None = None, external: bool = False
) -> Callable[[Request], Awaitable[AccessPrincipal]]:
    """A principal of the route's kind the policy allows ``code`` (on ``resource(request)`` when
    given)."""
    return _mark(
        _Requires(code, resource, external),
        AccessDeclaration("requires", code, external=external),
    )


def access_declarations(dependant: Dependant | None) -> tuple[AccessDeclaration, ...]:
    """The access markers among a route's top-level dependencies.

    Top level means the route's and its routers' ``dependencies=[...]`` and the endpoint's own
    ``Depends`` parameters. A marker nested inside a helper dependency does not count, so a shared
    helper can never declare access for every route that happens to use it.
    """
    if dependant is None:
        return ()
    return tuple(
        declaration
        for dep in dependant.dependencies
        if isinstance(declaration := getattr(dep.call, ACCESS_MARKER, None), AccessDeclaration)
    )


def _mounted_dependant(route: APIRoute, scope: Scope) -> Dependant | None:
    """The dependant of the route *as mounted for this request* (FastAPI 0.142 lazy includes).

    An included route carries the include's dependencies only in its effective route context,
    which FastAPI keeps in the scope; a route mounted twice has one context per mount.
    """
    getter = getattr(fastapi_routing, "_get_scope_effective_route_context", None)
    context = getter(scope) if getter is not None else None
    if context is not None and getattr(context, "original_route", None) is route:
        return getattr(context, "dependant", None)
    return route.dependant


class AccessCheckedRoute(APIRoute):
    """An ``APIRoute`` that answers 403 unless the route, as mounted, declares its access."""

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not access_declarations(_mounted_dependant(self, scope)):
            response = JSONResponse({"code": "FORBIDDEN", "permission": None}, status_code=403)
            await response(scope, receive, send)
            return
        await super().handle(scope, receive, send)
