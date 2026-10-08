"""Unit tests for the pure OIDC helpers (IDENTITY-01)."""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlsplit

import pytest

from aip.modules.identity.oidc import (
    OidcError,
    build_authorize_url,
    check_idp_binding,
    domain_of,
    new_code_verifier,
    new_nonce,
    new_state,
    safe_return_to,
)

AUTHORIZE = "https://kc.example.test/realms/aip/protocol/openid-connect/auth"


def _url(idp_alias: str | None) -> str:
    return build_authorize_url(
        authorize_endpoint=AUTHORIZE,
        client_id="aip-api",
        redirect_uri="https://app.example.test/api/v1/auth/oidc/callback",
        email="alice@kaefer.test",
        idp_alias=idp_alias,
        state=new_state(),
        nonce=new_nonce(),
        code_verifier=new_code_verifier(),
    )


def test_domain_of_lowercases() -> None:
    assert domain_of("Alice@Kaefer.TEST") == "kaefer.test"


@pytest.mark.parametrize(
    "value",
    ["no-at-sign", "@kaefer.test", "alice@", "a@b@kaefer.test", "alice@nodot", "x@exa mple.test"],
)
def test_domain_of_rejects_malformed(value: str) -> None:
    with pytest.raises(ValueError):
        domain_of(value)


def test_authorize_url_with_idp_hint() -> None:
    url = _url("kaefer-oidc")
    assert url.startswith(AUTHORIZE + "?")
    assert "code_challenge_method=S256" in url
    assert "kc_idp_hint=kaefer-oidc" in url
    assert "login_hint=alice%40kaefer.test" in url
    query = parse_qs(urlsplit(url).query)
    assert query["response_type"] == ["code"]
    assert "openid" in query["scope"][0].split()
    assert query["nonce"][0]
    assert query["code_challenge"][0]
    state = query["state"][0]
    raw = base64.urlsafe_b64decode(state + "=" * (-len(state) % 4))
    assert len(raw) >= 32


def test_authorize_url_without_idp_hint() -> None:
    assert "kc_idp_hint" not in _url(None)


def test_code_challenge_is_s256_of_the_verifier() -> None:
    import hashlib

    verifier = new_code_verifier()
    url = build_authorize_url(
        authorize_endpoint=AUTHORIZE,
        client_id="aip-api",
        redirect_uri="https://app.example.test/cb",
        email="a@b.test",
        idp_alias=None,
        state="s",
        nonce="n",
        code_verifier=verifier,
    )
    challenge = parse_qs(urlsplit(url).query)["code_challenge"][0]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert challenge == expected.decode()


def test_check_idp_binding_mismatch() -> None:
    with pytest.raises(OidcError) as exc:
        check_idp_binding("acme-oidc", "kaefer-oidc")
    assert exc.value.code == "IDP_TENANT_MISMATCH"
    assert exc.value.status_code == 403


def test_check_idp_binding_present_claim_without_cookie_alias() -> None:
    with pytest.raises(OidcError) as exc:
        check_idp_binding("acme-oidc", None)
    assert exc.value.code == "IDP_TENANT_MISMATCH"


def test_check_idp_binding_local_account_on_sso_domain() -> None:
    with pytest.raises(OidcError) as exc:
        check_idp_binding(None, "kaefer-oidc")
    assert exc.value.code == "SSO_REQUIRED"
    assert exc.value.status_code == 403


def test_check_idp_binding_passes() -> None:
    check_idp_binding(None, None)
    check_idp_binding("kaefer-oidc", "kaefer-oidc")


@pytest.mark.parametrize(
    "value",
    [
        "//evil.test/x",
        "https://evil.test",
        "/\\evil.test",
        "javascript:alert(1)",
        "",
        None,
        "projects",
        "/ok\nx",
        "/%2F%2Fevil.test",
    ],
)
def test_safe_return_to_rejects(value: str | None) -> None:
    assert safe_return_to(value) == "/"


@pytest.mark.parametrize("value", ["/projects?x=1", "/", "/a/b#c"])
def test_safe_return_to_keeps_same_origin_paths(value: str) -> None:
    assert safe_return_to(value) == value
