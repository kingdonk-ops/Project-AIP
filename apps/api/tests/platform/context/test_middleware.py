"""Integration and e2e tests for the request context middleware (ARCH-04)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import Depends, FastAPI

from aip.main import create_app
from aip.platform.context import Principal, RequestContext, get_context
from aip.platform.context.resolvers import PrincipalResolver

DEBUG = "/api/v1/_debug/context"


def make_app(
    principal_resolver: PrincipalResolver, membership_resolver: Any, *, env: str = "test"
) -> FastAPI:
    return create_app(
        principal_resolver=principal_resolver, membership_resolver=membership_resolver, env=env
    )


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class BarrierResolver:
    """Holds every request inside the middleware until ``n`` requests are in flight."""

    def __init__(self, inner: PrincipalResolver, n: int) -> None:
        self._inner = inner
        self._n = n
        self._arrived = 0
        self._all_in = asyncio.Event()

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        self._arrived += 1
        if self._arrived >= self._n:
            self._all_in.set()
        await asyncio.wait_for(self._all_in.wait(), timeout=5)
        return await self._inner.resolve(headers)


async def test_concurrent_requests_see_their_own_tenant(
    ids: Any, principal_resolver: Any, membership_resolver: Any
) -> None:
    app = make_app(BarrierResolver(principal_resolver, 2), membership_resolver)
    async with client(app) as c:
        ra, rb = await asyncio.gather(
            c.get(DEBUG, headers={"Authorization": "Bearer token-alice"}),
            c.get(DEBUG, headers={"Authorization": "Bearer token-bob"}),
        )
    assert ra.status_code == rb.status_code == 200
    assert ra.json()["tenant_id"] == str(ids.tenant_a)
    assert ra.json()["actor_id"] == str(ids.alice)
    assert ra.json()["asset_path_scope"] == ["site_a.unit_1"]
    assert rb.json()["tenant_id"] == str(ids.tenant_b)
    assert rb.json()["actor_id"] == str(ids.bob)


async def test_project_header_for_non_member_is_403(
    ids: Any, principal_resolver: Any, membership_resolver: Any
) -> None:
    app = make_app(principal_resolver, membership_resolver)
    async with client(app) as c:
        # Alice (tenant A) asks for tenant B's project.
        r = await c.get(
            DEBUG,
            headers={"Authorization": "Bearer token-alice", "X-Project-Id": str(ids.project_b1)},
        )
    assert r.status_code == 403
    assert r.headers["x-request-id"]


async def test_project_header_for_member_sets_project(
    ids: Any, principal_resolver: Any, membership_resolver: Any
) -> None:
    app = make_app(principal_resolver, membership_resolver)
    async with client(app) as c:
        r = await c.get(
            DEBUG,
            headers={"Authorization": "Bearer token-alice", "X-Project-Id": str(ids.project_a1)},
        )
    assert r.status_code == 200
    assert r.json()["project_id"] == str(ids.project_a1)


async def test_malformed_project_header_is_400(
    principal_resolver: Any, membership_resolver: Any
) -> None:
    app = make_app(principal_resolver, membership_resolver)
    async with client(app) as c:
        r = await c.get(
            DEBUG, headers={"Authorization": "Bearer token-alice", "X-Project-Id": "nope"}
        )
    assert r.status_code == 400


async def test_unauthenticated_request_to_scoped_route_is_401(
    principal_resolver: Any, membership_resolver: Any
) -> None:
    app = make_app(principal_resolver, membership_resolver)
    async with client(app) as c:
        r = await c.get(DEBUG)
        health = await c.get("/api/v1/health")
    assert r.status_code == 401
    assert health.status_code == 200
    assert health.headers["x-request-id"]


async def test_request_id_is_echoed_or_generated(
    principal_resolver: Any, membership_resolver: Any
) -> None:
    app = make_app(principal_resolver, membership_resolver)
    async with client(app) as c:
        given = await c.get(
            DEBUG, headers={"Authorization": "Bearer token-alice", "X-Request-Id": "abc-123"}
        )
        generated = await c.get(DEBUG, headers={"Authorization": "Bearer token-alice"})
        unsafe = await c.get(
            DEBUG, headers={"Authorization": "Bearer token-alice", "X-Request-Id": "x" * 500}
        )
    assert given.headers["x-request-id"] == "abc-123"
    assert given.json()["request_id"] == "abc-123"
    assert generated.headers["x-request-id"] == generated.json()["request_id"]
    assert len(generated.headers["x-request-id"]) >= 16
    assert unsafe.headers["x-request-id"] != "x" * 500


@pytest.mark.parametrize("env", ["production", "development", ""])
async def test_debug_route_only_mounted_in_test_env(
    env: str, principal_resolver: Any, membership_resolver: Any
) -> None:
    app = make_app(principal_resolver, membership_resolver, env=env)
    async with client(app) as c:
        r = await c.get(DEBUG, headers={"Authorization": "Bearer token-alice"})
    assert r.status_code == 404


async def test_env_defaults_to_aip_env(
    monkeypatch: pytest.MonkeyPatch, principal_resolver: Any, membership_resolver: Any
) -> None:
    monkeypatch.setenv("AIP_ENV", "test")
    app = create_app(principal_resolver=principal_resolver, membership_resolver=membership_resolver)
    async with client(app) as c:
        r = await c.get(DEBUG, headers={"Authorization": "Bearer token-alice"})
    assert r.status_code == 200


async def test_default_app_denies_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "test")
    async with client(create_app()) as c:
        r = await c.get(DEBUG, headers={"Authorization": "Bearer token-alice"})
    assert r.status_code == 401


def sync_tenant_dependency() -> UUID:
    """A sync FastAPI dependency runs in a worker thread (anyio.to_thread.run_sync)."""
    return get_context().tenant_id


@dataclass
class InMemoryAuditSink:
    records: list[dict[str, str]] = field(default_factory=list[dict[str, str]])

    def record(self, action: str) -> None:
        c: RequestContext = get_context()
        self.records.append(
            {"action": action, "tenant_id": str(c.tenant_id), "request_id": c.request_id}
        )


async def test_e2e_authenticated_call_is_audited_with_request_id(
    ids: Any, principal_resolver: Any, membership_resolver: Any
) -> None:
    sink = InMemoryAuditSink()
    app = make_app(principal_resolver, membership_resolver)

    @app.post("/api/v1/_test/widgets")
    async def create_widget(  # pyright: ignore[reportUnusedFunction]
        tenant_from_thread: UUID = Depends(sync_tenant_dependency),  # noqa: B008
    ) -> dict[str, str]:
        sink.record("widget.created")
        return {"tenant_from_thread": str(tenant_from_thread)}

    async with client(app) as c:
        r = await c.post("/api/v1/_test/widgets", headers={"Authorization": "Bearer token-alice"})
    assert r.status_code == 200
    request_id = r.headers["x-request-id"]
    assert request_id
    assert r.json() == {"tenant_from_thread": str(ids.tenant_a)}
    assert sink.records == [
        {"action": "widget.created", "tenant_id": str(ids.tenant_a), "request_id": request_id}
    ]
