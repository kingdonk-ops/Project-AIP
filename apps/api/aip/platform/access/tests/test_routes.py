"""Access declarations, ``AccessCheckedRoute`` and the startup route check (ACCESS-01 step 5)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Annotated
from uuid import UUID

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI, Request

from aip.platform.access import (
    AccessPrincipal,
    Catalogue,
    Grant,
    PermissionDef,
    PolicyService,
    ProjectScope,
    Resource,
    RouteAccessError,
    authenticated,
    install_access,
    public,
    requires,
)
from aip.platform.context import Principal, RequestContextMiddleware
from aip.platform.context.resolvers import DenyAllMembershipResolver

TENANT = UUID("00000000-0000-4000-8000-00000000000a")
ALICE = UUID("00000000-0000-4000-8000-0000000a11ce")
CATALOGUE = Catalogue(
    PermissionDef(c, "fixture", c) for c in ("fixture.item.read", "fixture.item.create")
)


class HeaderResolver:
    """``authorization: alice`` is alice in tenant A; anything else is anonymous."""

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        if headers.get("authorization") == "alice":
            return Principal(tenant_id=TENANT, actor_id=ALICE)
        return None


class Grants:
    def __init__(self, *grants: Grant) -> None:
        self.items = grants

    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        return self.items


def guarded_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/fixture")

    @router.get("/open", dependencies=[Depends(public())])
    async def open_route() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "open"}

    @router.get("/me")
    async def me(  # pyright: ignore[reportUnusedFunction]
        principal: Annotated[AccessPrincipal, Depends(authenticated())],
    ) -> dict[str, str]:
        return {"actor": str(principal.actor_id)}

    @router.get("/items", dependencies=[Depends(requires("fixture.item.read"))])
    async def items() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "items"}

    def project_of(request: Request) -> Resource:
        return Resource(project_id=request.query_params.get("project"))

    @router.post(
        "/items", dependencies=[Depends(requires("fixture.item.create", resource=project_of))]
    )
    async def create_item() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "created"}

    return router


def make_app(*grants: Grant, extra: APIRouter | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(guarded_router())
    if extra is not None:
        app.include_router(extra)
    install_access(app, catalogue=CATALOGUE, policy=PolicyService(CATALOGUE, [Grants(*grants)]))
    app.add_middleware(
        RequestContextMiddleware,
        principal_resolver=HeaderResolver(),
        membership_resolver=DenyAllMembershipResolver(),
    )
    return app


@pytest.fixture
def grants() -> list[Grant]:
    return []


@pytest.fixture
async def client(grants: list[Grant]) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=make_app(*grants))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


ALICE_HEADERS = {"authorization": "alice"}


def test_undeclared_route_stops_startup_naming_method_and_path() -> None:
    bad = APIRouter()

    @bad.get("/api/v1/fixture/unguarded")
    async def unguarded() -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    @bad.post("/api/v1/fixture/unguarded")
    async def unguarded_post() -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    with pytest.raises(RouteAccessError) as exc:
        make_app(extra=bad)
    assert "GET /api/v1/fixture/unguarded" in str(exc.value)
    assert "POST /api/v1/fixture/unguarded" in str(exc.value)
    assert "/api/v1/fixture/items" not in str(exc.value)


def test_requires_code_missing_from_the_catalogue_stops_startup() -> None:
    bad = APIRouter()

    @bad.get("/api/v1/fixture/ghost", dependencies=[Depends(requires("ghost.thing.read"))])
    async def ghost() -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    with pytest.raises(
        RouteAccessError, match=r"GET /api/v1/fixture/ghost requires ghost\.thing\.read"
    ):
        make_app(extra=bad)


async def test_route_added_after_startup_without_a_declaration_is_denied() -> None:
    app = make_app()

    @app.get("/api/v1/fixture/late")
    async def late() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"leak": "yes"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/api/v1/fixture/late", headers=ALICE_HEADERS)
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "permission": None}


async def test_public_route_needs_no_principal(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/fixture/open")).status_code == 200


async def test_authenticated_route(client: httpx.AsyncClient) -> None:
    anonymous = await client.get("/api/v1/fixture/me")
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"]["code"] == "NOT_AUTHENTICATED"
    signed_in = await client.get("/api/v1/fixture/me", headers=ALICE_HEADERS)
    assert signed_in.json() == {"actor": str(ALICE)}


async def test_requires_without_grants_is_403_naming_the_permission(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/fixture/items", headers=ALICE_HEADERS)
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "permission": "fixture.item.read"}


async def test_requires_without_principal_is_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/fixture/items")).status_code == 401


@pytest.mark.parametrize("grants", [[Grant("fixture.item.read")]])
async def test_requires_with_a_grant_is_200(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/fixture/items", headers=ALICE_HEADERS)
    assert response.status_code == 200


@pytest.mark.parametrize("grants", [[Grant("fixture.item.create", ProjectScope("p1"))]])
async def test_requires_checks_the_resolved_resource(client: httpx.AsyncClient) -> None:
    allowed = await client.post("/api/v1/fixture/items?project=p1", headers=ALICE_HEADERS)
    denied = await client.post("/api/v1/fixture/items?project=p2", headers=ALICE_HEADERS)
    assert allowed.status_code == 200
    assert denied.status_code == 403


async def test_a_declaration_added_by_include_router_counts() -> None:
    inner = APIRouter()

    @inner.get("/api/v1/fixture/by-include")
    async def by_include() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "yes"}

    outer = APIRouter()
    outer.include_router(inner, dependencies=[Depends(authenticated())])
    app = make_app(extra=outer)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/api/v1/fixture/by-include")).status_code == 401
        assert (await c.get("/api/v1/fixture/by-include", headers=ALICE_HEADERS)).status_code == 200


def test_undeclared_route_under_a_prefix_is_named_with_its_full_path() -> None:
    inner = APIRouter(prefix="/fixture")

    @inner.get("/unguarded")
    async def unguarded() -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    outer = APIRouter(prefix="/api/v1")
    outer.include_router(inner)
    with pytest.raises(RouteAccessError, match="GET /api/v1/fixture/unguarded"):
        make_app(extra=outer)


# --- review follow-ups: routes the startup check never saw, nested markers, foreign routes ------


async def get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, headers=ALICE_HEADERS)


async def test_router_included_after_startup_without_a_declaration_is_denied() -> None:
    app = make_app()
    late = APIRouter()

    @late.get("/api/v1/fixture/late-router")
    async def late_route() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"leak": "yes"}

    app.include_router(late)
    response = await get(app, "/api/v1/fixture/late-router")
    assert response.status_code == 403
    assert response.json() == {"code": "FORBIDDEN", "permission": None}


async def test_one_router_mounted_twice_is_checked_per_mount() -> None:
    app = make_app()
    shared = APIRouter()

    @shared.get("/thing")
    async def thing() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "yes"}

    app.include_router(shared, prefix="/api/v1/open", dependencies=[Depends(public())])
    app.include_router(shared, prefix="/api/v1/bare")
    assert (await get(app, "/api/v1/open/thing")).status_code == 200
    assert (await get(app, "/api/v1/bare/thing")).status_code == 403


async def test_route_added_to_an_already_included_router_is_denied() -> None:
    router = guarded_router()
    app = FastAPI()
    app.include_router(router)
    install_access(app, catalogue=CATALOGUE, policy=PolicyService(CATALOGUE))

    @router.get("/sneaky")
    async def sneaky() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"leak": "yes"}

    assert (await get(app, "/api/v1/fixture/sneaky")).status_code == 403


def test_a_marker_nested_in_a_helper_dependency_does_not_count() -> None:
    helper_marker = public()

    async def helper(_: None = Depends(helper_marker)) -> None:
        return None

    bad = APIRouter()

    @bad.get("/api/v1/fixture/helper-only", dependencies=[Depends(helper)])
    async def helper_only() -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    with pytest.raises(RouteAccessError, match="GET /api/v1/fixture/helper-only"):
        make_app(extra=bad)


def test_websocket_routes_stop_startup() -> None:
    bad = APIRouter()

    @bad.websocket("/api/v1/fixture/ws")
    async def ws(websocket: object) -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    with pytest.raises(RouteAccessError, match=r"cannot see.*/api/v1/fixture/ws"):
        make_app(extra=bad)


def test_fastapi_docs_routes_are_allowed() -> None:
    paths = {getattr(r, "path", None) for r in make_app().router.routes}
    assert {"/openapi.json", "/docs"} <= paths


async def test_a_context_without_an_actor_is_not_authenticated() -> None:
    class TenantOnly:
        async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
            return Principal(tenant_id=TENANT)

    app = FastAPI()
    app.include_router(guarded_router())
    install_access(app, catalogue=CATALOGUE, policy=PolicyService(CATALOGUE))
    app.add_middleware(
        RequestContextMiddleware,
        principal_resolver=TenantOnly(),
        membership_resolver=DenyAllMembershipResolver(),
    )
    assert (await get(app, "/api/v1/fixture/me")).status_code == 401
