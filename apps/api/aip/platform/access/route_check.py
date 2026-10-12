"""Startup enforcement of access declarations (ACCESS-01).

``install_access(app, ...)`` runs at the end of ``create_app()``, after every router is mounted:

1. ``check_routes`` raises ``RouteAccessError`` listing every ``METHOD path`` without an access
   declaration, every ``requires()`` code that is not in the catalogue, and every route that is
   not an ``APIRoute`` (websockets, ``app.mount`` sub-apps, ``add_route``) except FastAPI's own
   OpenAPI and docs pages. Routes are read as mounted (``fastapi.routing.iter_route_contexts``:
   full path, plus dependencies added by ``include_router``), since FastAPI includes routers
   lazily;
2. every ``APIRoute`` becomes an ``AccessCheckedRoute``, which checks the route as mounted for
   each request (FastAPI keeps a route's own class when a router is included, so module routes
   are converted here). Every router in the tree defaults to that class, and a router included
   later through ``app.include_router`` is converted on inclusion, so a route that declares
   nothing is denied at runtime with 403 even when the startup check never saw it;
3. the policy, catalogue and principal source go on ``app.state`` and ``Forbidden`` renders as
   403 ``{"code": "FORBIDDEN", "permission": code}``.

``aip.main`` runs ``check_routes`` and ``enforce_routes`` again in the lifespan startup, so routes
added between ``create_app()`` and serving fail startup too.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from functools import wraps
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute, APIRouter, RouteContext, iter_route_contexts
from starlette.routing import BaseRoute

from aip.platform.access.catalogue import Catalogue
from aip.platform.access.dependencies import (
    AccessCheckedRoute,
    PrincipalSource,
    access_declarations,
)
from aip.platform.access.policy import Forbidden, PolicyService

__all__ = ["RouteAccessError", "check_routes", "enforce_routes", "install_access"]


class RouteAccessError(RuntimeError):
    """Routes without an access declaration, or requiring permissions nobody declared."""


def _path(context: RouteContext) -> str:
    return context.path or str(getattr(context.original_route, "path", "") or "?")


def _labels(context: RouteContext) -> list[str]:
    methods = sorted(context.methods or ()) or ["ANY"]
    return [f"{method} {_path(context)}" for method in methods]


def _framework_paths(app: FastAPI | None) -> frozenset[str]:
    """FastAPI's own OpenAPI and docs pages (public by design; no tenant data)."""
    if app is None:
        return frozenset()
    paths = {app.openapi_url, app.docs_url, app.redoc_url}
    if app.docs_url and app.swagger_ui_oauth2_redirect_url:
        paths.add(app.swagger_ui_oauth2_redirect_url)
    return frozenset(p for p in paths if p)


def check_routes(
    routes: Sequence[BaseRoute], catalogue: Mapping[str, object], app: FastAPI | None = None
) -> None:
    """Raise ``RouteAccessError`` naming every undeclared, unknown-permission or foreign route."""
    allowed_foreign = _framework_paths(app)
    undeclared: list[str] = []
    unknown: list[str] = []
    foreign: list[str] = []
    for context in iter_route_contexts(routes):
        if not isinstance(context.original_route, APIRoute):
            if _path(context) not in allowed_foreign:
                foreign.extend(_labels(context))
            continue
        declarations = access_declarations(context.dependant)
        if not declarations:
            undeclared.extend(_labels(context))
        for declaration in declarations:
            code = declaration.permission
            if code is not None and code not in catalogue:
                unknown.extend(f"{label} requires {code}" for label in _labels(context))
    problems: list[str] = []
    if undeclared:
        problems.append(
            "routes without public(), authenticated() or requires(): " + ", ".join(undeclared)
        )
    if unknown:
        problems.append("permissions missing from the catalogue: " + ", ".join(unknown))
    if foreign:
        problems.append(
            "routes the access check cannot see (websocket, mount or add_route): "
            + ", ".join(foreign)
        )
    if problems:
        raise RouteAccessError("; ".join(problems))


def _routers(router: APIRouter) -> Iterator[APIRouter]:
    yield router
    for route in router.routes:
        included: object = getattr(route, "original_router", None)  # FastAPI 0.142 lazy include
        if isinstance(included, APIRouter):
            yield from _routers(included)


def enforce_routes(app: FastAPI) -> None:
    """Make every mounted ``APIRoute`` an ``AccessCheckedRoute`` and the default route class."""
    for router in _routers(app.router):
        router.route_class = AccessCheckedRoute
    for context in iter_route_contexts(app.router.routes):
        route = context.original_route
        if isinstance(route, APIRoute) and not isinstance(route, AccessCheckedRoute):
            route.__class__ = AccessCheckedRoute  # same layout; adds only the runtime check


def _enforce_after_include(app: FastAPI) -> None:
    include: Callable[..., Any] = app.router.include_router

    @wraps(include)
    def include_router(*args: Any, **kwargs: Any) -> Any:
        result = include(*args, **kwargs)
        enforce_routes(app)
        return result

    app.router.include_router = include_router  # pyright: ignore[reportAttributeAccessIssue]


def install_access(
    app: FastAPI,
    *,
    catalogue: Catalogue,
    policy: PolicyService,
    principal_source: PrincipalSource | None = None,
) -> None:
    check_routes(app.router.routes, catalogue, app)
    enforce_routes(app)
    _enforce_after_include(app)
    app.state.access_catalogue = catalogue
    app.state.access_policy = policy
    app.state.access_principal_source = principal_source

    @app.exception_handler(Forbidden)
    async def forbidden(request: Request, exc: Forbidden) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"code": "FORBIDDEN", "permission": exc.permission}, status_code=403)
