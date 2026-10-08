"""Static lint of the Keycloak realms as code (IDENTITY-01 steps 1-3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[6]
KEYCLOAK = ROOT / "infra" / "keycloak"


@pytest.fixture(scope="module")
def realm() -> dict[str, Any]:
    return json.loads((KEYCLOAK / "realm-aip.json").read_text(encoding="utf-8"))


def _client(realm: dict[str, Any], client_id: str) -> dict[str, Any]:
    return next(c for c in realm["clients"] if c["clientId"] == client_id)


def test_realm_policy(realm: dict[str, Any]) -> None:
    assert realm["realm"] == "aip"
    assert realm["registrationAllowed"] is False
    assert realm["verifyEmail"] is True and realm["resetPasswordAllowed"] is True
    assert realm["bruteForceProtected"] is True
    assert realm["failureFactor"] == 5
    assert realm["permanentLockout"] is False
    assert realm["waitIncrementSeconds"] == 60
    assert realm["maxFailureWaitSeconds"] == 900
    assert realm["maxDeltaTimeSeconds"] == 43200
    policy = realm["passwordPolicy"]
    for part in ("length(12)", "maxLength(128)", "notUsername", "notEmail", "passwordHistory(5)",
                 "passwordBlacklist(password-blocklist.txt)", "hashAlgorithm(argon2)"):
        assert part in policy
    assert realm["browserFlow"] == "aip-browser"
    assert realm["loginTheme"] == "aip"
    assert "accountTheme" not in realm
    assert json.loads(realm["attributes"]["acr.loa.map"]) == {"aal1": 1, "aal2": 2}
    assert realm["organizationsEnabled"] is True


def test_otp_and_webauthn_policy(realm: dict[str, Any]) -> None:
    assert (realm["otpPolicyType"], realm["otpPolicyAlgorithm"]) == ("totp", "HmacSHA1")
    assert (realm["otpPolicyDigits"], realm["otpPolicyPeriod"], realm["otpPolicyLookAheadWindow"]) == (6, 30, 1)
    assert realm["webAuthnPolicySignatureAlgorithms"] == ["ES256", "RS256"]
    assert realm["webAuthnPolicyUserVerificationRequirement"] == "preferred"
    assert realm["webAuthnPolicyPasswordlessUserVerificationRequirement"] == "required"
    enabled = {a["alias"] for a in realm["requiredActions"] if a["enabled"]}
    assert {"VERIFY_EMAIL", "UPDATE_PASSWORD", "CONFIGURE_TOTP", "webauthn-register",
            "webauthn-register-passwordless"} <= enabled


def test_api_client(realm: dict[str, Any]) -> None:
    api = _client(realm, "aip-api")
    assert api["publicClient"] is False
    assert api["standardFlowEnabled"] is True
    assert api["directAccessGrantsEnabled"] is False
    assert api["implicitFlowEnabled"] is False
    assert api["serviceAccountsEnabled"] is False
    attrs = api["attributes"]
    assert attrs["pkce.code.challenge.method"] == "S256"
    assert attrs["minimum.acr.value"] == "aal2"
    assert attrs["default.acr.values"] == "aal2"
    assert attrs["backchannel.logout.session.required"] == "true"
    assert attrs["backchannel.logout.url"].endswith("/api/v1/auth/oidc/backchannel-logout")
    assert sorted(u.rsplit("}", 1)[-1] for u in api["redirectUris"]) == [
        "/api/v1/auth/oidc/callback",
        "/login",
    ]
    mappers = {m["protocolMapper"]: m for m in api["protocolMappers"]}
    assert mappers["oidc-usersessionmodel-note-mapper"]["config"]["claim.name"] == "identity_provider"
    assert mappers["oidc-usersessionmodel-note-mapper"]["config"]["id.token.claim"] == "true"
    assert mappers["oidc-amr-mapper"]["config"]["id.token.claim"] == "true"
    assert {"basic", "acr"} <= set(api["defaultClientScopes"])


def test_admin_client_has_user_roles_only(realm: dict[str, Any]) -> None:
    admin = _client(realm, "aip-admin")
    assert admin["serviceAccountsEnabled"] is True
    assert admin["standardFlowEnabled"] is False
    assert admin["directAccessGrantsEnabled"] is False
    sa = next(u for u in realm["users"] if u.get("serviceAccountClientId") == "aip-admin")
    roles = sa["clientRoles"]["realm-management"]
    assert sorted(roles) == ["manage-users", "query-users", "view-users"]
    assert "manage-realm" not in roles
    assert set(sa.get("realmRoles", [])) <= {"default-roles-aip"}


def test_organizations_and_brokers(realm: dict[str, Any]) -> None:
    orgs = {o["alias"]: o for o in realm["organizations"]}
    assert orgs["kaefer-demo"]["domains"] == [{"name": "kaefer.test", "verified": True}]
    assert orgs["tenant-b"]["domains"] == [{"name": "acme.test", "verified": True}]
    assert [i["alias"] for i in orgs["kaefer-demo"]["identityProviders"]] == ["kaefer-oidc"]
    assert [i["alias"] for i in orgs["tenant-b"]["identityProviders"]] == ["acme-oidc"]
    idps = {i["alias"]: i for i in realm["identityProviders"]}
    for alias, domain in (("kaefer-oidc", "kaefer.test"), ("acme-oidc", "acme.test")):
        idp = idps[alias]
        assert idp["hideOnLogin"] is True
        assert idp["config"]["kc.org.domain"] == domain
        assert idp["config"]["kc.org.broker.redirect.mode.email-matches"] == "true"
        assert "/realms/mock-idp/" in idp["config"]["authorizationUrl"]
        assert idp["config"]["pkceEnabled"] == "true"
        assert idp["firstBrokerLoginFlowAlias"] == "aip-first-broker-login"


def _flow(realm: dict[str, Any], alias: str) -> list[dict[str, Any]]:
    return next(f for f in realm["authenticationFlows"] if f["alias"] == alias)[
        "authenticationExecutions"
    ]


def _config(realm: dict[str, Any], alias: str) -> dict[str, str]:
    return next(c for c in realm["authenticatorConfig"] if c["alias"] == alias)["config"]


def test_browser_flow(realm: dict[str, Any]) -> None:
    top = _flow(realm, "aip-browser")
    assert all(e["requirement"] == "ALTERNATIVE" for e in top)
    names = [e.get("authenticator") or e["flowAlias"] for e in top]
    assert names == ["auth-cookie", "identity-provider-redirector", "aip-organization", "aip-forms"]
    loa1 = _flow(realm, "aip-forms-loa1")
    assert _config(realm, loa1[0]["authenticatorConfig"])["loa-condition-level"] == "1"
    first = {e["authenticator"]: e for e in _flow(realm, "aip-first-factor")}
    assert first["auth-username-password-form"]["requirement"] == "ALTERNATIVE"
    pwd = _config(realm, first["auth-username-password-form"]["authenticatorConfig"])
    assert pwd["default.reference.value"] == "pwd"
    passkey = _config(realm, first["webauthn-authenticator-passwordless"]["authenticatorConfig"])
    assert passkey["default.reference.value"] == "hwk"
    loa2 = _flow(realm, "aip-forms-loa2")
    assert _config(realm, loa2[0]["authenticatorConfig"])["loa-condition-level"] == "2"
    # Keycloak allows one LoA condition per level: a passkey satisfies level 2 by skipping the
    # second factor (Condition - credential: webauthn-passwordless not used).
    second = _flow(realm, "aip-second-factor")
    assert _config(realm, second[0]["authenticatorConfig"])["credentials"] == "webauthn-passwordless"
    key = {e["authenticator"]: e for e in _flow(realm, "aip-2fa-key")}
    otp = {e["authenticator"]: e for e in _flow(realm, "aip-2fa-otp")}
    assert _config(realm, key["webauthn-authenticator"]["authenticatorConfig"])["default.reference.value"] == "hwk"
    # REQUIRED, so a user with no second factor gets CONFIGURE_TOTP at first sign-in.
    assert otp["auth-otp-form"]["requirement"] == "REQUIRED"
    assert _config(realm, otp["auth-otp-form"]["authenticatorConfig"])["default.reference.value"] == "otp"
    levels = [
        c["config"]["loa-condition-level"]
        for c in realm["authenticatorConfig"]
        if "loa-condition-level" in c["config"]
    ]
    assert len(levels) == len(set(levels)), "one LoA condition per level"
    review = _flow(realm, "aip-first-broker-login")[0]
    assert _config(realm, review["authenticatorConfig"])["update.profile.on.first.login"] == "off"


def test_no_real_secrets(realm: dict[str, Any]) -> None:
    text = (KEYCLOAK / "realm-aip.json").read_text(encoding="utf-8")
    mock = (KEYCLOAK / "realm-mock-idp.json").read_text(encoding="utf-8")
    for client in realm["clients"]:
        assert "dev_only" in client["secret"] and client["secret"].startswith("${")
    assert "dev_only" in mock
    assert "BEGIN PRIVATE KEY" not in text + mock


def test_mock_idp_users() -> None:
    mock = json.loads((KEYCLOAK / "realm-mock-idp.json").read_text(encoding="utf-8"))
    assert mock["realm"] == "mock-idp"
    assert {u["email"] for u in mock["users"]} == {"alice@kaefer.test", "bob@acme.test"}


def test_theme_files() -> None:
    theme = KEYCLOAK / "themes" / "aip" / "login"
    props = (theme / "theme.properties").read_text(encoding="utf-8")
    assert "parent=keycloak.v2" in props and "css/aip.css" in props
    assert (theme / "resources" / "css" / "aip.css").is_file()
    assert (theme / "messages" / "messages_en.properties").is_file()
    assert (KEYCLOAK / "password-blocklist.txt").read_text(encoding="utf-8").strip()
