"""IDENTITY-03 unit tests: cookies, expiry, aal, CSRF, logout-token claims, Keycloak admin, job."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from starlette.datastructures import Headers
from starlette.responses import Response

from aip.modules.identity import jobs
from aip.modules.identity.csrf import csrf_ok
from aip.modules.identity.keycloak_admin import (
    KeycloakAdmin,
    KeycloakAdminError,
    KeycloakAdminSettings,
)
from aip.modules.identity.oidc import BACKCHANNEL_LOGOUT_EVENT, OidcError, check_logout_claims
from aip.modules.identity.sessions import (
    DEFAULT_POLICY,
    Expiry,
    IssuedSession,
    clear_session_cookies,
    compute_expiry,
    derive_aal,
    set_session_cookies,
    touch,
)
from aip.modules.ops.api import JobView

ORIGIN = "https://app.example.test"
STAFF = DEFAULT_POLICY["staff"]


def _at(hh: int, mm: int) -> datetime:
    return datetime(2026, 10, 13, hh, mm, tzinfo=UTC)


def test_session_cookie_attributes() -> None:
    issued = IssuedSession(uuid4(), "sid-value", "csrf-value", compute_expiry(_at(10, 0), STAFF))
    response = Response()
    set_session_cookies(response, issued)
    cookies = response.headers.getlist("set-cookie")
    sid = next(c for c in cookies if c.startswith("__Host-aip_sid="))
    csrf = next(c for c in cookies if c.startswith("__Host-aip_csrf="))
    for part in ("Secure", "HttpOnly", "SameSite=lax", "Path=/"):
        assert part.lower() in sid.lower(), sid
    assert "domain" not in sid.lower()
    assert "httponly" not in csrf.lower() and "secure" in csrf.lower()

    cleared = Response()
    clear_session_cookies(cleared)
    assert all("Max-Age=0" in c for c in cleared.headers.getlist("set-cookie"))


def test_expiry_is_idle_capped_by_absolute() -> None:
    expiry = compute_expiry(_at(10, 0), STAFF)
    assert (expiry.idle_expires_at, expiry.absolute_expires_at) == (_at(10, 30), _at(22, 0))
    assert touch(_at(10, 20), expiry, STAFF).idle_expires_at == _at(10, 50)
    late = touch(_at(21, 50), expiry, STAFF)
    assert late == Expiry(idle_expires_at=_at(22, 0), absolute_expires_at=_at(22, 0))


def test_derive_aal() -> None:
    assert derive_aal("aal2", ["pwd", "otp"]) == 2
    assert derive_aal(None, ["pwd"]) == 1
    assert derive_aal(None, ["hwk"]) == 2


def _headers(**values: str) -> Headers:
    return Headers({k.replace("_", "-"): v for k, v in values.items()})


COOKIES = "__Host-aip_sid=s; __Host-aip_csrf=tok"


@pytest.mark.parametrize(
    ("method", "path", "headers", "ok"),
    [
        (
            "POST",
            "/api/v1/auth/logout",
            {"cookie": COOKIES, "origin": ORIGIN, "x_csrf_token": "tok"},
            True,
        ),
        ("POST", "/api/v1/auth/logout", {"cookie": COOKIES, "origin": ORIGIN}, False),
        (
            "POST",
            "/api/v1/auth/logout",
            {"cookie": COOKIES, "origin": "https://evil.test", "x_csrf_token": "tok"},
            False,
        ),
        ("POST", "/api/v1/auth/logout", {"cookie": COOKIES, "x_csrf_token": "tok"}, False),
        (
            "DELETE",
            "/api/v1/me/sessions/x",
            {"cookie": COOKIES, "origin": ORIGIN, "x_csrf_token": "nope"},
            False,
        ),
        ("GET", "/api/v1/me", {"cookie": COOKIES}, True),
        ("POST", "/api/v1/auth/login/start", {"origin": "https://evil.test"}, False),
        ("POST", "/api/v1/auth/login/start", {"origin": ORIGIN}, True),
        ("POST", "/api/v1/auth/oidc/backchannel-logout", {"cookie": COOKIES}, True),
        ("POST", "/api/v1/projects", {"cookie": COOKIES, "authorization": "Bearer abc"}, False),
        ("POST", "/api/v1/projects", {"authorization": "Bearer abc"}, True),
        ("POST", "/api/v1/projects", {}, True),  # no session cookie: nothing to forge
    ],
)
def test_csrf_rules(method: str, path: str, headers: dict[str, str], ok: bool) -> None:
    assert csrf_ok(method, path, _headers(**headers), ORIGIN) is ok


ISSUER = "https://kc.example.test/realms/aip"


def _logout_claims(**overrides: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": "aip-api",
        "iat": 1_000_000,
        "jti": "j",
        "sid": "kc-sid-1",
        "events": {BACKCHANNEL_LOGOUT_EVENT: {}},
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def test_logout_token_claims() -> None:
    check = lambda c: check_logout_claims(c, issuer=ISSUER, client_id="aip-api", now=1_000_010)  # noqa: E731
    assert check(_logout_claims()) == "kc-sid-1"
    for bad in (
        _logout_claims(events=None),
        _logout_claims(nonce="n"),
        _logout_claims(sid=None),
        _logout_claims(aud="other"),
        _logout_claims(iat=1_000_000 - 400),
    ):
        with pytest.raises(OidcError) as exc:
            check(bad)
        assert exc.value.status_code == 400


def _admin(handler: Any) -> tuple[KeycloakAdmin, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        return handler(request)

    settings = KeycloakAdminSettings.model_validate(
        {"KEYCLOAK_URL": "https://kc.example.test", "KEYCLOAK_ADMIN_CLIENT_SECRET": SecretStr("s")}
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return KeycloakAdmin(settings, http), seen


async def test_keycloak_admin_revocation_is_idempotent() -> None:
    admin, seen = _admin(lambda r: httpx.Response(404 if "gone" in r.url.path else 204))
    await admin.revoke_kc_session("live")
    await admin.revoke_kc_session("gone")  # already ended: success
    await admin.logout_user("u1")
    calls = [(r.method, r.url.path) for r in seen if not r.url.path.endswith("/token")]
    assert calls == [
        ("DELETE", "/admin/realms/aip/sessions/live"),
        ("DELETE", "/admin/realms/aip/sessions/gone"),
        ("POST", "/admin/realms/aip/users/u1/logout"),
    ]
    assert sum(r.url.path.endswith("/token") for r in seen) == 1  # the token is reused


async def test_keycloak_admin_raises_on_server_errors() -> None:
    admin, _ = _admin(lambda r: httpx.Response(500))
    with pytest.raises(KeycloakAdminError):
        await admin.revoke_kc_session("x")


async def test_the_job_revokes_every_sid_and_can_run_twice() -> None:
    admin, seen = _admin(lambda r: httpx.Response(404))
    job = JobView.model_validate(
        {
            "id": uuid4(),
            "tenant_id": uuid4(),
            "job_type": jobs.sessions.REVOKE_KEYCLOAK_JOB,
            "status": "running",
            "idempotency_key": None,
            "correlation_id": uuid4(),
            "attempts": 1,
            "payload": {"kc_sids": ["a", "b"]},
            "result_ref": None,
            "error": None,
            "requested_by": None,
            "procrastinate_job_id": 1,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )
    for _ in range(2):
        await jobs.revoke_keycloak_sessions(None, job, admin)  # pyright: ignore[reportArgumentType]
    deletes = [r.url.path for r in seen if r.method == "DELETE"]
    assert deletes == ["/admin/realms/aip/sessions/a", "/admin/realms/aip/sessions/b"] * 2
    assert json.loads(json.dumps(job.payload)) == {"kc_sids": ["a", "b"]}
