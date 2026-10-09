"""``GET /api/v1/me`` and the JIT callback over HTTP, against real Postgres (IDENTITY-02).

The app runs in process with its real wiring: the ``x-test-principal`` stub (``AIP_ENV=test`` +
``AUTH_TEST_STUB=1``), tenancy's ``require_active_tenant`` and the process ``aip_app`` engine
pointed at the test database through ``DATABASE_URL``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.fixtures.postgres import TenantDb

from aip.main import create_app
from aip.modules.identity import repository as repo
from aip.modules.identity.api import JitLoginHandler, get_external_login_handler
from aip.modules.identity.jit import JitProvisioner
from aip.modules.identity.oidc import KeycloakOidcClient
from aip.modules.identity.routes import get_login_rate_limiter, get_login_service
from aip.modules.identity.service import LoginRateLimiter, LoginService
from aip.modules.identity.settings import IdentitySettings
from aip.platform.db.engine import dispose_engine

from .conftest import TENANT_A_ID, TENANT_B_ID, FakeDirectory, StubProvider, seed_sql

ALICE = "alice@kaefer.test"
BOB = "bob@acme.test"


@pytest.fixture
async def app(idb: TenantDb, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", idb.db.app_url)
    await dispose_engine()
    yield create_app(env="test", tracing=False)
    await dispose_engine()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://app.example.test") as c:
        yield c


def principal(tenant_id: UUID, user_id: UUID, **overrides: Any) -> dict[str, str]:
    body: dict[str, Any] = {
        "kind": "user",
        "tenantId": str(tenant_id),
        "userId": str(user_id),
        "userClass": "staff",
        "sessionId": None,
        "aal": 1,
        "amr": ["fed"],
    }
    body.update(overrides)
    return {"x-test-principal": json.dumps(body)}


async def seed_user(db: TenantDb, tenant: UUID, email: str, status: str = "active") -> UUID:
    async with db.with_tenant(tenant) as conn:
        user_id = await repo.insert_user(
            conn,
            tenant_id=tenant,
            email=email,
            display_name=email.split("@")[0].title(),
            user_class="staff",
            status=status,  # type: ignore[arg-type]
            sso_managed=True,
        )
        await repo.insert_membership(
            conn, tenant_id=tenant, user_id=user_id, membership_type="member"
        )
    return user_id


async def test_me_returns_the_callers_own_user_tenant_and_memberships(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    r = await client.get("/api/v1/me", headers=principal(TENANT_A_ID, alice, aal=2, amr=["otp"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant"] == {"id": str(TENANT_A_ID), "slug": "kaefer-demo", "name": "Kaefer Demo"}
    assert body["user"] == {
        "id": str(alice),
        "email": ALICE,
        "displayName": "Alice",
        "userClass": "staff",
        "status": "active",
    }
    [membership] = body["memberships"]
    assert membership["membershipType"] == "member" and membership["validTo"] is None
    assert body["aal"] == 2 and body["amr"] == ["otp"]
    assert r.headers["cache-control"] == "no-store"


async def test_same_email_in_both_tenants_never_leaks(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    a = await seed_user(idb, TENANT_A_ID, "shared@client.test")
    b = await seed_user(idb, TENANT_B_ID, "shared@client.test")
    ra = await client.get("/api/v1/me", headers=principal(TENANT_A_ID, a))
    rb = await client.get("/api/v1/me", headers=principal(TENANT_B_ID, b))
    assert ra.status_code == rb.status_code == 200
    assert ra.json()["user"]["id"] == str(a) and ra.json()["tenant"]["slug"] == "kaefer-demo"
    assert rb.json()["user"]["id"] == str(b) and rb.json()["tenant"]["slug"] == "tenant-b"
    assert str(b) not in ra.text and str(TENANT_B_ID) not in ra.text
    assert str(a) not in rb.text and str(TENANT_A_ID) not in rb.text


async def test_a_principal_naming_another_tenants_user_gets_401(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    bob = await seed_user(idb, TENANT_B_ID, BOB)
    for headers in (principal(TENANT_B_ID, alice), principal(TENANT_A_ID, bob)):
        r = await client.get("/api/v1/me", headers=headers)
        assert r.status_code == 401
        assert r.json() == {"detail": {"code": "NOT_AUTHENTICATED", "message": "not authenticated"}}
        assert ALICE not in r.text and BOB not in r.text


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"x-test-principal": "{not json"},
        {"x-test-principal": json.dumps({"kind": "user", "userClass": "admin"})},
        {"authorization": "Bearer token-alice"},
    ],
)
async def test_no_principal_is_401(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    r = await client.get("/api/v1/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "NOT_AUTHENTICATED"


async def test_unknown_deactivated_or_invited_user_is_401(
    idb: TenantDb, client: httpx.AsyncClient
) -> None:
    gone = await seed_user(idb, TENANT_A_ID, "gone@kaefer.test")
    invited = await seed_user(idb, TENANT_A_ID, "inv@kaefer.test", status="invited")
    async with idb.with_tenant(TENANT_A_ID) as conn:
        await repo.set_user_status(conn, gone, "deactivated")
    for user_id in (gone, invited, uuid4()):
        r = await client.get("/api/v1/me", headers=principal(TENANT_A_ID, user_id))
        assert r.status_code == 401, r.text
        assert r.json()["detail"]["code"] == "NOT_AUTHENTICATED"


async def test_soft_deleted_user_is_401(idb: TenantDb, client: httpx.AsyncClient) -> None:
    user_id = await seed_user(idb, TENANT_A_ID, ALICE)
    await seed_sql(idb, f"UPDATE app_user SET deleted_at = now() WHERE id = '{user_id}'")
    r = await client.get("/api/v1/me", headers=principal(TENANT_A_ID, user_id))
    assert r.status_code == 401


@pytest.mark.parametrize(
    ("status", "code"), [("suspended", "TENANT_SUSPENDED"), ("offboarded", "TENANT_OFFBOARDED")]
)
async def test_inactive_tenant_is_403_without_naming_it(
    idb: TenantDb, client: httpx.AsyncClient, status: str, code: str
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    await seed_sql(idb, f"UPDATE tenants SET status = '{status}' WHERE id = '{TENANT_A_ID}'")
    r = await client.get("/api/v1/me", headers=principal(TENANT_A_ID, alice))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == code
    assert "kaefer" not in r.text.lower() and ALICE not in r.text


async def test_me_is_absent_without_the_stub(
    idb: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = await seed_user(idb, TENANT_A_ID, ALICE)
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.delenv("AUTH_TEST_STUB", raising=False)
    app = create_app(env="test", tracing=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://app.example.test"
    ) as c:
        r = await c.get("/api/v1/me", headers=principal(TENANT_A_ID, alice))
    assert r.status_code == 401


async def test_me_is_in_the_openapi_document(app: FastAPI) -> None:
    op = app.openapi()["paths"]["/api/v1/me"]["get"]
    assert op["operationId"] == "identity_get_me"
    schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/MeResponse")


# --- the OIDC callback runs JIT (in-process Keycloak stub; the real one is in e2e) -----------


@pytest.fixture
async def login_client(
    idb: TenantDb,
    app: FastAPI,
    settings: IdentitySettings,
    oidc_client: KeycloakOidcClient,
) -> AsyncIterator[httpx.AsyncClient]:
    service = LoginService(settings, FakeDirectory(), oidc_client)
    limiter = LoginRateLimiter.from_redis_url(None)
    jit = JitLoginHandler(JitProvisioner(connect=idb.with_tenant, connect_pre=idb.no_tenant))
    app.dependency_overrides[get_login_service] = lambda: service
    app.dependency_overrides[get_login_rate_limiter] = lambda: limiter
    app.dependency_overrides[get_external_login_handler] = lambda: jit
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://app.example.test") as c:
        yield c


async def _sign_in(
    client: httpx.AsyncClient, provider: StubProvider, login_email: str, **claims: Any
) -> httpx.Response:
    r = await client.post("/api/v1/auth/login/start", json={"email": login_email})
    assert r.status_code == 200, r.text
    code = provider.authorize(r.json()["redirectUrl"], **claims)
    state = r.json()["redirectUrl"].split("state=")[1].split("&")[0]
    return await client.get("/api/v1/auth/oidc/callback", params={"code": code, "state": state})


async def test_callback_provisions_alice_once(
    idb: TenantDb, login_client: httpx.AsyncClient, provider: StubProvider
) -> None:
    sub = str(uuid4())
    first = await _sign_in(login_client, provider, ALICE, sub=sub)
    assert first.status_code == 200, first.text
    assert first.json()["action"] == "created"
    second = await _sign_in(login_client, provider, ALICE, sub=sub)
    assert second.status_code == 200, second.text
    assert second.json() == {"userId": first.json()["userId"], "action": "refreshed"}
    assert "eyJ" not in second.text  # no Keycloak token reaches the browser
    async with idb.with_tenant(TENANT_A_ID) as conn:
        page = await repo.list_users(conn)
    assert [str(u.id) for u in page.items] == [first.json()["userId"]]
    async with idb.with_tenant(TENANT_B_ID) as conn:
        assert (await repo.list_users(conn)).items == []


async def test_callback_refusal_is_403_and_names_nothing(
    login_client: httpx.AsyncClient, provider: StubProvider
) -> None:
    # alice's own login, but kaefer's IdP asserts an acme.test address.
    r = await _sign_in(login_client, provider, ALICE, sub=str(uuid4()), email=BOB)
    assert r.status_code == 403
    assert r.json()["code"] == "DOMAIN_NOT_CLAIMED"
    assert "acme" not in r.text and "kaefer" not in r.text and "@" not in r.text
    assert r.headers["cache-control"] == "no-store"
