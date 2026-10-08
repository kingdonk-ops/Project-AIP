"""Unit tests for tenant resolution (TENANCY-01 steps 3-5). No database: a fake tenant loader.

The integration tests in ``test_tenants_db.py`` repeat the important paths on real Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

import httpx
import pytest
from fastapi import Depends, FastAPI
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID, FixturePrincipalResolver

from aip.main import create_app
from aip.modules.tenancy.api import TenantView, require_active_tenant
from aip.modules.tenancy.dependencies import get_tenant_service, parse_tenant_id
from aip.modules.tenancy.service import TenantAccessError, access_for_status
from aip.platform.context import Principal, get_context

NOBODY_TENANT = UUID("00000000-0000-4000-8000-0000000000ff")


def view(tenant_id: UUID, slug: str, status: str = "active") -> TenantView:
    return TenantView.model_validate(
        {
            "id": tenant_id,
            "name": slug.title(),
            "slug": slug,
            "region_code": "ap-southeast-2",
            "deployment_shape": "pooled",
            "status": status,
        }
    )


class FakeTenants:
    """Stands in for ``TenantService``; records every lookup."""

    def __init__(self, *views: TenantView) -> None:
        self.views = {v.id: v for v in views}
        self.calls: list[UUID] = []

    async def get(self, tenant_id: UUID) -> TenantView | None:
        self.calls.append(tenant_id)
        return self.views.get(tenant_id)


@pytest.fixture
def tenants() -> FakeTenants:
    return FakeTenants(view(TENANT_A_ID, "kaefer-demo"), view(TENANT_B_ID, "tenant-b"))


@pytest.fixture
def app(tenants: FakeTenants) -> FastAPI:
    resolver = FixturePrincipalResolver(
        {
            "token-alice": Principal(tenant_id=TENANT_A_ID, actor_id=ALICE_ID),
            "token-bob": Principal(tenant_id=TENANT_B_ID, actor_id=BOB_ID),
            "token-unknown": Principal(tenant_id=NOBODY_TENANT),
            "token-bad-uuid": Principal(tenant_id="not-a-uuid"),  # pyright: ignore[reportArgumentType]
            "token-no-tenant": Principal(tenant_id=None),  # pyright: ignore[reportArgumentType]
            "token-nil": Principal(tenant_id=UUID(int=0)),
        }
    )
    application = create_app(env="test", principal_resolver=resolver, tracing=False)
    application.dependency_overrides[get_tenant_service] = lambda: tenants

    async def guarded(
        tenant: Annotated[TenantView, Depends(require_active_tenant)],
    ) -> dict[str, Any]:
        ctx = get_context()
        return {
            "tenant_id": str(ctx.tenant_id),
            "tenant_slug": ctx.tenant_slug,
            "region_code": ctx.region_code,
            "view_slug": tenant.slug,
        }

    application.add_api_route("/api/v1/_test/guarded", guarded, methods=["GET"])
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- status map -------------------------------------------------------------------------------


def test_active_allows() -> None:
    assert access_for_status("active") is None


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("suspended", "TENANT_SUSPENDED"),
        ("offboarding", "TENANT_OFFBOARDED"),
        ("offboarded", "TENANT_OFFBOARDED"),
        ("provisioning", "TENANT_NOT_READY"),
    ],
)
def test_inactive_statuses_deny_with_their_code(status: str, code: str) -> None:
    denial = access_for_status(status)
    assert denial is not None
    assert (denial.status_code, denial.code) == (403, code)


@pytest.mark.parametrize("status", ["", "ACTIVE", "deleted", "unknown"])
def test_unknown_status_fails_closed(status: str) -> None:
    denial = access_for_status(status)
    assert denial is not None and denial.status_code == 403


# --- parse_tenant_id --------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["not-a-uuid", "", None, 42, UUID(int=0), str(UUID(int=0))])
def test_parse_tenant_id_rejects_with_401(raw: object) -> None:
    with pytest.raises(TenantAccessError) as info:
        parse_tenant_id(raw)
    assert info.value.status_code == 401


def test_parse_tenant_id_accepts_uuid_and_string() -> None:
    assert parse_tenant_id(TENANT_A_ID) == TENANT_A_ID
    assert parse_tenant_id(str(TENANT_B_ID)) == TENANT_B_ID


# --- require_active_tenant over HTTP ----------------------------------------------------------


async def test_principal_tenant_is_mapped_into_the_context(
    client: httpx.AsyncClient, tenants: FakeTenants
) -> None:
    resp = await client.get("/api/v1/_test/guarded", headers=bearer("token-alice"))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "tenant_id": str(TENANT_A_ID),
        "tenant_slug": "kaefer-demo",
        "region_code": "ap-southeast-2",
        "view_slug": "kaefer-demo",
    }
    assert tenants.calls == [TENANT_A_ID]


async def test_each_principal_gets_only_its_own_tenant(
    client: httpx.AsyncClient, tenants: FakeTenants
) -> None:
    resp = await client.get("/api/v1/me/tenant", headers=bearer("token-bob"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["slug"] == "tenant-b"
    assert body["regionCode"] == "ap-southeast-2"
    assert "kaefer" not in resp.text
    assert tenants.calls == [TENANT_B_ID]


@pytest.mark.parametrize(
    "headers", [{}, bearer("token-unknown-to-resolver"), {"Authorization": "Basic x"}]
)
async def test_no_principal_is_401_before_any_tenant_query(
    client: httpx.AsyncClient, tenants: FakeTenants, headers: dict[str, str]
) -> None:
    for path in ("/api/v1/_test/guarded", "/api/v1/me/tenant"):
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 401, resp.text
    assert tenants.calls == []


@pytest.mark.parametrize("token", ["token-bad-uuid", "token-no-tenant", "token-nil"])
async def test_principal_without_a_valid_tenant_is_401_before_any_query(
    client: httpx.AsyncClient, tenants: FakeTenants, token: str
) -> None:
    resp = await client.get("/api/v1/me/tenant", headers=bearer(token))
    assert resp.status_code == 401, resp.text
    assert tenants.calls == []


async def test_unknown_tenant_is_401(client: httpx.AsyncClient, tenants: FakeTenants) -> None:
    resp = await client.get("/api/v1/me/tenant", headers=bearer("token-unknown"))
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"]["code"] == "TENANT_UNKNOWN"
    assert tenants.calls == [NOBODY_TENANT]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("suspended", "TENANT_SUSPENDED"),
        ("offboarding", "TENANT_OFFBOARDED"),
        ("offboarded", "TENANT_OFFBOARDED"),
        ("provisioning", "TENANT_NOT_READY"),
    ],
)
async def test_inactive_tenant_is_403_on_every_guarded_route(
    client: httpx.AsyncClient, tenants: FakeTenants, status: str, code: str
) -> None:
    tenants.views[TENANT_B_ID] = view(TENANT_B_ID, "tenant-b", status)
    for path in ("/api/v1/_test/guarded", "/api/v1/me/tenant"):
        resp = await client.get(path, headers=bearer("token-bob"))
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == code
        assert "tenant-b" not in resp.text
    # The other tenant is unaffected.
    resp = await client.get("/api/v1/me/tenant", headers=bearer("token-alice"))
    assert resp.status_code == 200
