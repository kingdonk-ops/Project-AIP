"""IDENTITY-10 unit tests: the portal audience's cookies, CSRF, principal, policy cap, JIT rule,
settings and back-channel logout audiences. No database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from starlette.datastructures import Headers
from starlette.responses import Response

from aip.modules.identity.csrf import csrf_ok
from aip.modules.identity.jit import decide_jit
from aip.modules.identity.oidc import BACKCHANNEL_LOGOUT_EVENT, OidcError, check_logout_claims
from aip.modules.identity.principal import Principal
from aip.modules.identity.repository import UserRow
from aip.modules.identity.session_store import select_session_cookie
from aip.modules.identity.sessions import (
    IssuedSession,
    audience_allows,
    clear_session_cookies,
    compute_expiry,
    cookie_names,
    policy_for,
    set_session_cookies,
)
from aip.modules.identity.settings import IdentitySettingsError

from .conftest import make_settings

APP = "https://app.example.test"
PORTAL = "https://portal.example.test"
STAFF_SID, STAFF_CSRF = "__Host-aip_sid", "__Host-aip_csrf"
PORTAL_SID, PORTAL_CSRF = "__Host-aip_portal_sid", "__Host-aip_portal_csrf"


# --- which cookie -------------------------------------------------------------------------------


def test_one_cookie_selects_its_audience_on_any_path() -> None:
    assert select_session_cookie("/api/v1/me", {STAFF_SID: "s"}) == ("app", "s")
    assert select_session_cookie("/api/v1/me", {PORTAL_SID: "p"}) == ("portal", "p")
    assert select_session_cookie("/api/v1/portal/me", {STAFF_SID: "s"}) == ("app", "s")
    assert select_session_cookie("/api/v1/me", {}) is None
    assert select_session_cookie("/api/v1/me", {STAFF_SID: ""}) is None
    assert select_session_cookie("/api/v1/me", {STAFF_SID: "x" * 129}) is None


def test_both_cookies_select_by_path() -> None:
    both = {STAFF_SID: "s", PORTAL_SID: "p"}
    assert select_session_cookie("/api/v1/portal/x", both) == ("portal", "p")
    assert select_session_cookie("/api/v1/auth/portal/login/start", both) == ("portal", "p")
    assert select_session_cookie("/api/v1/me", both) == ("app", "s")
    assert select_session_cookie("/api/v1/portalx", both) == ("app", "s")


def test_audience_allows_portal_users_only_in_portal_sessions() -> None:
    assert audience_allows("portal", "portal")
    assert audience_allows("app", "staff")
    assert audience_allows("app", "field")
    assert audience_allows("device", "field")
    assert not audience_allows("app", "portal")
    assert not audience_allows("portal", "staff")
    assert not audience_allows("device", "portal")


# --- cookies ------------------------------------------------------------------------------------


def _issued(audience: Any) -> IssuedSession:
    now = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
    policy = policy_for({}, "portal")
    return IssuedSession(uuid4(), "sid-value", "csrf-value", compute_expiry(now, policy), audience)


def _set_cookies(response: Response) -> list[str]:
    return [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]


def test_portal_session_sets_only_the_portal_cookies() -> None:
    response = Response()
    set_session_cookies(response, _issued("portal"))
    cookies = _set_cookies(response)
    assert len(cookies) == 2
    sid = next(c for c in cookies if c.startswith(f"{PORTAL_SID}=sid-value"))
    csrf = next(c for c in cookies if c.startswith(f"{PORTAL_CSRF}=csrf-value"))
    for header in (sid, csrf):
        assert "Secure" in header and "Path=/" in header and "Domain" not in header
    assert "HttpOnly" in sid and "HttpOnly" not in csrf
    assert not any(c.startswith(("__Host-aip_sid=", "__Host-aip_csrf=")) for c in cookies)


def test_clear_session_cookies_clears_one_audience_only() -> None:
    portal = Response()
    clear_session_cookies(portal, audience="portal")
    names = sorted(c.split("=", 1)[0] for c in _set_cookies(portal))
    assert names == [PORTAL_CSRF, PORTAL_SID]
    staff = Response()
    clear_session_cookies(staff)
    assert sorted(c.split("=", 1)[0] for c in _set_cookies(staff)) == [STAFF_CSRF, STAFF_SID]


def test_device_audience_has_no_browser_cookie() -> None:
    with pytest.raises(ValueError):
        cookie_names("device")


# --- CSRF ---------------------------------------------------------------------------------------


def _csrf(path: str, cookies: dict[str, str], **headers: str) -> bool:
    raw = {"cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()), **headers}
    if not cookies:
        raw.pop("cookie")
    return csrf_ok("POST", path, Headers(raw), APP, PORTAL)


def test_csrf_portal_cookie_needs_the_portal_origin_and_token() -> None:
    portal = {PORTAL_SID: "p", PORTAL_CSRF: "tok"}
    path = "/api/v1/portal/logout"
    assert _csrf(path, portal, origin=PORTAL, **{"x-csrf-token": "tok"})
    assert not _csrf(path, portal, origin=APP, **{"x-csrf-token": "tok"})
    assert not _csrf(path, portal, origin=PORTAL, **{"x-csrf-token": "other"})
    assert not _csrf(path, portal, origin=PORTAL)
    # The staff token does not stand in for the portal one.
    mixed = {PORTAL_SID: "p", STAFF_CSRF: "tok"}
    assert not _csrf(path, mixed, origin=PORTAL, **{"x-csrf-token": "tok"})


def test_csrf_staff_cookie_is_refused_from_the_portal_origin() -> None:
    staff = {STAFF_SID: "s", STAFF_CSRF: "tok"}
    assert _csrf("/api/v1/auth/logout", staff, origin=APP, **{"x-csrf-token": "tok"})
    assert not _csrf("/api/v1/auth/logout", staff, origin=PORTAL, **{"x-csrf-token": "tok"})


def test_csrf_with_both_cookies_checks_the_selected_one() -> None:
    both = {STAFF_SID: "s", STAFF_CSRF: "st", PORTAL_SID: "p", PORTAL_CSRF: "pt"}
    assert _csrf("/api/v1/portal/x", both, origin=PORTAL, **{"x-csrf-token": "pt"})
    assert not _csrf("/api/v1/portal/x", both, origin=APP, **{"x-csrf-token": "st"})
    assert _csrf("/api/v1/things", both, origin=APP, **{"x-csrf-token": "st"})
    assert not _csrf("/api/v1/things", both, origin=PORTAL, **{"x-csrf-token": "pt"})


def test_csrf_portal_login_start_checks_the_portal_origin_only() -> None:
    path = "/api/v1/auth/portal/login/start"
    assert _csrf(path, {}, origin=PORTAL)
    assert _csrf(path, {})
    assert not _csrf(path, {}, origin=APP)
    assert not _csrf("/api/v1/auth/login/start", {}, origin=PORTAL)
    assert _csrf("/api/v1/auth/login/start", {}, origin=APP)


# --- principal ----------------------------------------------------------------------------------


def _principal(**extra: Any) -> Principal:
    body: dict[str, Any] = {
        "kind": "user",
        "tenantId": str(uuid4()),
        "userId": str(uuid4()),
        "aal": 2,
        **extra,
    }
    return Principal.model_validate(body)


def test_principal_audience_defaults_from_the_user_class() -> None:
    assert _principal(userClass="portal").audience == "portal"
    assert _principal(userClass="staff").audience == "app"
    assert _principal(userClass="field", audience="device").audience == "device"
    assert Principal.model_validate_json(
        _principal(userClass="portal").model_dump_json(by_alias=True)
    ).audience == "portal"


# --- policy -------------------------------------------------------------------------------------


def test_portal_idle_is_capped_at_staff_idle() -> None:
    raw = {"staff": {"idleMin": 10}, "portal": {"idleMin": 20, "absoluteH": 4}}
    portal = policy_for(raw, "portal")
    assert portal.idle == timedelta(minutes=10)
    assert portal.absolute == timedelta(hours=4)
    assert policy_for({}, "portal").idle == timedelta(minutes=15)
    assert policy_for({}, "staff").idle == timedelta(minutes=30)
    assert policy_for({"portal": {"idleMin": 5}}, "portal").idle == timedelta(minutes=5)
    # Staff policy is never touched by the cap.
    assert policy_for(raw, "staff").idle == timedelta(minutes=10)


# --- JIT ----------------------------------------------------------------------------------------


def _user(user_class: Any, status: Any = "active") -> UserRow:
    return UserRow(id=uuid4(), user_class=user_class, status=status)


def test_decide_jit_keeps_portal_users_on_the_portal() -> None:
    portal_user = _user("portal")
    staff_user = _user("staff")
    refused = decide_jit(portal_user, True, True, False, matched_by_subject=True)
    assert refused.reason == "PORTAL_SIGN_IN_REQUIRED"
    refused = decide_jit(staff_user, True, True, False, matched_by_subject=True, audience="portal")
    assert refused.reason == "STAFF_SIGN_IN_REQUIRED"
    refused = decide_jit(None, True, True, True, audience="portal")
    assert refused.reason == "STAFF_SIGN_IN_REQUIRED"
    invited = _user("portal", "invited")
    assert decide_jit(invited, True, True, False, audience="portal").kind == "link"
    assert decide_jit(None, True, True, False, audience="portal").reason == "NOT_INVITED"
    assert (
        decide_jit(portal_user, True, True, False, matched_by_subject=True, audience="portal").kind
        == "refresh"
    )


# --- settings -----------------------------------------------------------------------------------


def test_portal_settings() -> None:
    settings = make_settings(PORTAL_ORIGIN="https://portal.example.test/")
    assert settings.portal_oidc_client_id == "aip-portal"
    assert settings.portal_redirect_uri == (
        "https://portal.example.test/api/v1/auth/portal/oidc/callback"
    )
    assert not settings.portal_configured
    assert make_settings(PORTAL_OIDC_CLIENT_SECRET="s").portal_configured


def test_the_dev_portal_secret_is_refused_when_deployed() -> None:
    make_settings(PORTAL_OIDC_CLIENT_SECRET="aip_portal_dev_only_secret")  # test: allowed
    deployed = {
        "AIP_ENV": "production",
        "OIDC_CLIENT_SECRET": "a-real-secret",
        "PREAUTH_COOKIE_KEY": "cmVhbC1rZXktcmVhbC1rZXktcmVhbC1rZXktcmVhbC0",
    }
    assert make_settings(**deployed, PORTAL_OIDC_CLIENT_SECRET="real").portal_configured
    with pytest.raises((IdentitySettingsError, ValueError), match="PORTAL_OIDC_CLIENT_SECRET"):
        make_settings(**deployed, PORTAL_OIDC_CLIENT_SECRET="aip_portal_dev_only_secret")


# --- back-channel logout ------------------------------------------------------------------------


def test_logout_tokens_for_the_portal_client_are_accepted() -> None:
    now = 1_800_000_000.0
    claims = {
        "iss": "https://kc/realms/aip",
        "aud": "aip-portal",
        "iat": now,
        "events": {BACKCHANNEL_LOGOUT_EVENT: {}},
        "sid": "kc-sid",
    }
    kw: dict[str, Any] = {"issuer": "https://kc/realms/aip", "client_id": "aip-api", "now": now}
    with pytest.raises(OidcError):
        check_logout_claims(claims, **kw)
    assert check_logout_claims(claims, **kw, also_audiences=("aip-portal",)) == "kc-sid"
    with pytest.raises(OidcError):
        check_logout_claims({**claims, "aud": "other"}, **kw, also_audiences=("aip-portal",))
