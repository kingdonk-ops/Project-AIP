"""The external (portal) route allow-list (PORTAL-02 step 2): deny by default both ways, with 404.

An external principal reaches only routes declared ``external=True``, which must sit under
``/api/v1/portal/``; an internal principal never reaches those. ``check_routes`` refuses a route
flagged outside the prefix, and an unflagged route inside it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request

from aip.platform.access import (
    EXTERNAL_PREFIXES,
    AccessPrincipal,
    Catalogue,
    PermissionDef,
    PolicyService,
    RouteAccessError,
    authenticated,
    check_routes,
    install_access,
    public,
    requires,
)

TENANT = UUID("00000000-0000-4000-8000-00000000000a")
USER = UUID("00000000-0000-4000-8000-0000000a11ce")
CATALOGUE = Catalogue(
    PermissionDef(c, "fixture", c) for c in ("project.view", "portal.record.view")
)


def _app(router: APIRouter) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_the_portal_prefix_is_the_only_external_prefix() -> None:
    assert EXTERNAL_PREFIXES == ("/api/v1/portal/",)


def test_an_external_route_outside_the_portal_prefix_refuses_start() -> None:
    router = APIRouter()

    @router.get("/api/v1/projects", dependencies=[Depends(requires("project.view", external=True))])
    async def projects() -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    with pytest.raises(RouteAccessError, match=r"external routes outside .*GET /api/v1/projects"):
        check_routes(_app(router).router.routes, CATALOGUE)


@pytest.mark.parametrize(
    "declaration",
    [requires("portal.record.view"), authenticated(), public()],
    ids=["requires", "authenticated", "public"],
)
def test_a_portal_route_without_the_flag_refuses_start(declaration: object) -> None:
    router = APIRouter()

    @router.get("/api/v1/portal/x", dependencies=[Depends(declaration)])  # pyright: ignore[reportArgumentType]
    async def x() -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    with pytest.raises(RouteAccessError, match=r"not declared external=True: GET /api/v1/portal/x"):
        check_routes(_app(router).router.routes, CATALOGUE)


def test_flagged_portal_routes_and_unflagged_staff_routes_start() -> None:
    app = _test_app()
    check_routes(app.router.routes, CATALOGUE, app)


async def _principal(request: Request) -> AccessPrincipal | None:
    who = request.headers.get("authorization")
    if who not in ("external", "internal"):
        return None
    return AccessPrincipal(tenant_id=TENANT, actor_id=USER, external=who == "external")


def _test_app() -> FastAPI:
    router = APIRouter(prefix="/api/v1")

    @router.get("/portal/ping", dependencies=[Depends(authenticated(external=True))])
    async def ping() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "portal"}

    @router.get("/things", dependencies=[Depends(authenticated())])
    async def things() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "things"}

    @router.get("/items", dependencies=[Depends(requires("project.view"))])
    async def items() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "items"}

    return _app(router)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = _test_app()
    install_access(
        app, catalogue=CATALOGUE, policy=PolicyService(CATALOGUE), principal_source=_principal
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.parametrize(
    ("who", "portal", "staff"),
    [("external", 200, 404), ("internal", 404, 200), (None, 401, 401)],
)
async def test_each_kind_of_principal_reaches_only_its_own_routes(
    client: httpx.AsyncClient, who: str | None, portal: int, staff: int
) -> None:
    headers = {"authorization": who} if who else {}
    ping = await client.get("/api/v1/portal/ping", headers=headers)
    things = await client.get("/api/v1/things", headers=headers)
    assert (ping.status_code, things.status_code) == (portal, staff)
    for res in (ping, things):
        if res.status_code == 404:
            assert res.json() == {"code": "NOT_FOUND"}  # not 403: the other API stays unmapped
        if res.status_code == 401:
            assert res.json()["detail"]["code"] == "NOT_AUTHENTICATED"


async def test_an_external_principal_never_reaches_a_requires_route(
    client: httpx.AsyncClient,
) -> None:
    # Hidden before the policy is even asked (an internal user without grants gets 403 here).
    res = await client.get("/api/v1/items", headers={"authorization": "external"})
    assert (res.status_code, res.json()) == (404, {"code": "NOT_FOUND"})
    internal = await client.get("/api/v1/items", headers={"authorization": "internal"})
    assert internal.status_code == 403
