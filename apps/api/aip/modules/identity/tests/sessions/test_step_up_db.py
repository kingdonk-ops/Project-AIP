"""IDENTITY-04 step-up with real sessions on Postgres: the start redirect, the callback that rotates
the session to ``aal=2``, its refusals, and ``step_up()`` on a critical route."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.identity.oidc import KeycloakOidcClient
from aip.modules.identity.preauth_cookie import COOKIE_NAME as PREAUTH
from aip.modules.identity.routes import get_login_service
from aip.modules.identity.service import LoginService
from aip.modules.identity.sessions import IssuedSession
from aip.modules.identity.settings import IdentitySettings
from aip.platform.access import AccessPrincipal, Grant

from ..conftest import FakeDirectory, StubProvider
from .conftest import cookies, new_session, su_execute, su_fetch, unsafe

ALICE_KC = UUID("00000000-0000-4000-8000-00000000a1c1")
BOB_KC = UUID("00000000-0000-4000-8000-00000000b0b1")


class AllIdentityGrants:
    async def grants(self, principal: AccessPrincipal) -> Iterable[Grant]:
        return [Grant("identity.user.manage"), Grant("identity.user.read")]


@pytest.fixture
async def linked(db: TenantDb) -> None:
    await su_execute(
        db,
        f"UPDATE app_user SET keycloak_user_id = '{ALICE_KC}', sso_managed = true,"
        f" idp_alias = 'kaefer-oidc' WHERE id = '{ALICE_ID}';"
        f"UPDATE app_user SET keycloak_user_id = '{BOB_KC}', sso_managed = true,"
        f" idp_alias = 'acme-oidc' WHERE id = '{BOB_ID}'",
    )


@pytest.fixture
def service(
    app: FastAPI, settings: IdentitySettings, oidc_client: KeycloakOidcClient
) -> LoginService:
    login = LoginService(settings, FakeDirectory(), oidc_client)
    app.dependency_overrides[get_login_service] = lambda: login
    app.state.access_policy.register(AllIdentityGrants())
    return login


async def _start(client: httpx.AsyncClient, issued: IssuedSession) -> tuple[str, str]:
    r = await client.get(
        "/api/v1/auth/step-up/start",
        params={"returnTo": "/settings/users"},
        headers=cookies(issued),
    )
    assert r.status_code == 303, r.text
    preauth = r.cookies.get(PREAUTH)
    assert preauth
    return r.headers["location"], preauth


async def _callback(
    client: httpx.AsyncClient, provider: StubProvider, issued: IssuedSession, **claims: object
) -> httpx.Response:
    location, preauth = await _start(client, issued)
    code = provider.authorize(location, **claims)
    state = parse_qs(urlsplit(location).query)["state"][0]
    return await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": code, "state": state},
        headers={"cookie": f"{PREAUTH}={preauth}; __Host-aip_sid={issued.sid}"},
    )


def _sid(response: httpx.Response) -> str:
    raw = next(
        c for c in response.headers.get_list("set-cookie") if c.startswith("__Host-aip_sid=")
    )
    return raw.split(";", 1)[0].split("=", 1)[1]


async def test_start_redirects_to_a_forced_second_factor(
    client: httpx.AsyncClient, linked: None, service: LoginService
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID)
    location, _ = await _start(client, issued)
    q = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
    assert (q["prompt"], q["max_age"], q["acr_values"]) == ("login", "0", "aal2")
    assert q["kc_idp_hint"] == "kaefer-oidc" and q["login_hint"] == "alice@kaefer.test"


async def test_start_needs_a_session(client: httpx.AsyncClient, service: LoginService) -> None:
    r = await client.get("/api/v1/auth/step-up/start")
    assert r.status_code == 401


async def test_step_up_rotates_the_session_to_aal2(
    client: httpx.AsyncClient,
    db: TenantDb,
    linked: None,
    service: LoginService,
    provider: StubProvider,
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID, aal=1)
    r = await _callback(client, provider, issued, sub=str(ALICE_KC), upstream_amr=["pwd", "mfa"])
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/settings/users"
    new_sid = _sid(r)
    assert new_sid != issued.sid
    old = await su_fetch(
        db, "SELECT revoke_reason FROM user_session WHERE id = $1", issued.session_id
    )
    assert old == [("rotated",)]
    live = await su_fetch(
        db, "SELECT aal, amr FROM user_session WHERE user_id = $1 AND revoked_at IS NULL", ALICE_ID
    )
    assert len(live) == 1 and live[0][0] == 2 and "fed" in live[0][1] and "mfa" in live[0][1]
    enrolled = await su_fetch(db, "SELECT mfa_enrolled_at FROM app_user WHERE id = $1", ALICE_ID)
    assert enrolled[0][0] is not None
    me = await client.get("/api/v1/me", headers={"cookie": f"__Host-aip_sid={new_sid}"})
    assert me.status_code == 200 and me.json()["aal"] == 2


async def test_an_idp_without_mfa_is_refused_and_the_session_kept(
    client: httpx.AsyncClient,
    db: TenantDb,
    linked: None,
    service: LoginService,
    provider: StubProvider,
) -> None:
    issued = await new_session(TENANT_B_ID, BOB_ID, aal=1)
    r = await _callback(client, provider, issued, sub=str(BOB_KC), upstream_amr=["pwd"])
    assert r.status_code == 403
    assert r.json()["code"] == "MFA_NOT_SATISFIED"
    row = await su_fetch(
        db, "SELECT aal, revoked_at FROM user_session WHERE id = $1", issued.session_id
    )
    assert row == [(1, None)]


async def test_another_account_cannot_confirm(
    client: httpx.AsyncClient,
    db: TenantDb,
    linked: None,
    service: LoginService,
    provider: StubProvider,
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID, aal=1)
    r = await _callback(client, provider, issued, sub=str(uuid4()), upstream_amr=["mfa"])
    assert r.status_code == 403
    assert r.json()["code"] == "STEP_UP_SUBJECT_MISMATCH"
    events = await su_fetch(
        db, "SELECT detail->>'reason' FROM auth_event WHERE event_type = 'step_up.denied'"
    )
    assert events == [("step_up_subject_mismatch",)]


async def test_a_critical_action_needs_a_fresh_step_up_then_succeeds(
    client: httpx.AsyncClient,
    db: TenantDb,
    linked: None,
    service: LoginService,
    provider: StubProvider,
) -> None:
    issued = await new_session(TENANT_A_ID, ALICE_ID, aal=2)
    await su_execute(
        db,
        "UPDATE user_session SET authenticated_at = now() - interval '11 minutes' "
        f"WHERE id = '{issued.session_id}'",
    )
    body = {"email": "erin@client.test", "firstName": "Erin", "lastName": "Client"}
    r = await client.post("/api/v1/identity/invites", json=body, headers=unsafe(issued))
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["code"] == "STEP_UP_REQUIRED"

    done = await _callback(client, provider, issued, sub=str(ALICE_KC), upstream_amr=["mfa"])
    assert done.status_code == 303, done.text
    csrf = (
        next(c for c in done.headers.get_list("set-cookie") if c.startswith("__Host-aip_csrf="))
        .split(";", 1)[0]
        .split("=", 1)[1]
    )
    elevated = IssuedSession(
        session_id=issued.session_id, sid=_sid(done), csrf=csrf, expiry=issued.expiry
    )
    retried = await client.post("/api/v1/identity/invites", json=body, headers=unsafe(elevated))
    assert retried.status_code == 201, retried.text
