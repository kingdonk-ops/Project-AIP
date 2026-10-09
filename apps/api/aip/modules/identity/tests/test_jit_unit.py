"""IDENTITY-02 unit tests: ``decide_jit``, the ``Principal`` model and the test-auth stub guard.

No database. The integration tests are in ``test_jit_db.py`` and ``test_me_db.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from aip.main import create_app
from aip.modules.identity.jit import JitDecision, decide_jit
from aip.modules.identity.principal import (
    TEST_PRINCIPAL_HEADER,
    PlatformPrincipalAdapter,
    Principal,
    StubHeaderPrincipalResolver,
    stub_principal_resolver,
)
from aip.modules.identity.repository import UserRow

TENANT_A_ID = UUID("00000000-0000-4000-8000-00000000000a")
USER_ID = UUID("00000000-0000-4000-8000-0000000a11ce")
KC_ID = UUID("00000000-0000-4000-8000-00000000c0de")


def _principal_json(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "kind": "user",
        "tenantId": str(TENANT_A_ID),
        "userId": str(USER_ID),
        "userClass": "staff",
        "sessionId": None,
        "aal": 1,
        "amr": ["fed"],
    }
    data.update(overrides)
    return data


# --- decide_jit (the spec's cases first) --------------------------------------------------------


def test_new_sso_user_with_a_claimed_domain_is_created() -> None:
    d = decide_jit(existing=None, email_verified=True, domain_claimed=True, via_sso=True)
    assert str(d) == "create"
    assert d == JitDecision("create")


def test_local_login_without_a_user_is_not_invited() -> None:
    d = decide_jit(existing=None, email_verified=True, domain_claimed=False, via_sso=False)
    assert str(d) == "refuse:NOT_INVITED"


def test_sso_login_never_links_an_active_local_account() -> None:
    d = decide_jit(
        existing=UserRow(sso_managed=False, status="active"),
        email_verified=True,
        domain_claimed=True,
        via_sso=True,
    )
    assert str(d) == "refuse:ACCOUNT_LINK_REQUIRED"


def test_local_login_links_an_invited_local_user() -> None:
    d = decide_jit(
        existing=UserRow(sso_managed=False, status="invited"),
        email_verified=True,
        domain_claimed=False,
        via_sso=False,
    )
    assert str(d) == "link"


def test_unverified_email_is_refused() -> None:
    d = decide_jit(existing=None, email_verified=False, domain_claimed=True, via_sso=True)
    assert str(d) == "refuse:EMAIL_NOT_VERIFIED"


@pytest.mark.parametrize("via_sso", [True, False])
@pytest.mark.parametrize("matched_by_subject", [True, False])
def test_deactivated_user_is_refused(via_sso: bool, matched_by_subject: bool) -> None:
    d = decide_jit(
        existing=UserRow(status="deactivated", sso_managed=via_sso),
        email_verified=True,
        domain_claimed=True,
        via_sso=via_sso,
        matched_by_subject=matched_by_subject,
    )
    assert str(d) == "refuse:USER_DEACTIVATED"


# --- decide_jit: every other path ---------------------------------------------------------------


def test_sso_login_from_an_unclaimed_domain_is_refused_first() -> None:
    linked = UserRow(sso_managed=True, keycloak_user_id=KC_ID)
    for existing, by_subject in ((None, False), (linked, True)):
        d = decide_jit(existing, True, False, True, matched_by_subject=by_subject)
        assert str(d) == "refuse:DOMAIN_NOT_CLAIMED"


def test_soft_deleted_user_is_refused() -> None:
    gone = UserRow(sso_managed=True, deleted_at=datetime.now(UTC))
    assert str(decide_jit(gone, True, True, True)) == "refuse:USER_REMOVED"
    assert str(decide_jit(gone, True, True, True, matched_by_subject=True)) == (
        "refuse:USER_REMOVED"
    )


def test_linked_user_is_refreshed_even_with_an_unverified_email() -> None:
    user = UserRow(sso_managed=True, keycloak_user_id=KC_ID, status="active")
    assert str(decide_jit(user, False, True, True, matched_by_subject=True)) == "refresh"
    invited = UserRow(sso_managed=False, keycloak_user_id=KC_ID, status="invited")
    assert str(decide_jit(invited, True, False, False, matched_by_subject=True)) == "refresh"


def test_linked_local_account_signing_in_through_sso_is_refused() -> None:
    local = UserRow(sso_managed=False, keycloak_user_id=KC_ID)
    d = decide_jit(local, True, True, True, matched_by_subject=True)
    assert str(d) == "refuse:ACCOUNT_LINK_REQUIRED"


def test_sso_user_signing_in_with_a_local_password_is_refused() -> None:
    sso = UserRow(sso_managed=True, keycloak_user_id=KC_ID)
    assert str(decide_jit(sso, True, True, False, matched_by_subject=True)) == (
        "refuse:SSO_REQUIRED"
    )
    unlinked = UserRow(sso_managed=True, status="invited")
    assert str(decide_jit(unlinked, True, True, False)) == "refuse:SSO_REQUIRED"


def test_sso_user_found_by_email_is_linked() -> None:
    for status in ("invited", "active"):
        user = UserRow(sso_managed=True, status=status)  # type: ignore[arg-type]
        assert str(decide_jit(user, True, True, True)) == "link"


def test_email_already_linked_to_another_keycloak_account_is_never_relinked() -> None:
    other = UserRow(sso_managed=True, keycloak_user_id=KC_ID)
    assert str(decide_jit(other, True, True, True)) == "refuse:ACCOUNT_LINK_REQUIRED"
    local = UserRow(sso_managed=False, status="invited", keycloak_user_id=KC_ID)
    assert str(decide_jit(local, True, False, False)) == "refuse:ACCOUNT_LINK_REQUIRED"


def test_active_local_user_without_a_keycloak_link_is_not_linked_by_email() -> None:
    user = UserRow(sso_managed=False, status="active")
    assert str(decide_jit(user, True, False, False)) == "refuse:ACCOUNT_LINK_REQUIRED"


def test_unverified_email_never_links() -> None:
    invited = UserRow(sso_managed=False, status="invited")
    assert str(decide_jit(invited, False, False, False)) == "refuse:EMAIL_NOT_VERIFIED"
    assert str(decide_jit(None, False, False, False)) == "refuse:EMAIL_NOT_VERIFIED"


# --- Principal ----------------------------------------------------------------------------------


def test_principal_rejects_an_unknown_user_class_at_user_class() -> None:
    with pytest.raises(ValidationError) as info:
        Principal.model_validate(_principal_json(userClass="admin"))
    assert [e["loc"] for e in info.value.errors()] == [("userClass",)]


def test_principal_round_trips_camel_case() -> None:
    p = Principal.model_validate(_principal_json(aal=2, amr=["pwd", "otp"]))
    assert p.tenant_id == TENANT_A_ID and p.user_id == USER_ID and p.aal == 2
    assert p.model_dump(by_alias=True, mode="json")["userClass"] == "staff"


@pytest.mark.parametrize(
    "overrides",
    [
        {"tenantId": "00000000-0000-0000-0000-000000000000"},
        {"userId": "00000000-0000-0000-0000-000000000000"},
        {"aal": 3},
        {"kind": "client"},
        {"tenantId": "not-a-uuid"},
        {"extra": "field"},
    ],
)
def test_principal_rejects_bad_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Principal.model_validate(_principal_json(**overrides))


# --- the test-auth stub guard --------------------------------------------------------------------


def test_create_app_refuses_the_stub_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    with pytest.raises(RuntimeError, match="test auth stub forbidden in production"):
        create_app(tracing=False)


@pytest.mark.parametrize("flag", ["1", "true", "yes"])
def test_any_stub_flag_is_refused_in_production(monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    monkeypatch.setenv("AUTH_TEST_STUB", flag)
    with pytest.raises(RuntimeError, match="forbidden in production"):
        stub_principal_resolver("production")
    with pytest.raises(RuntimeError, match="forbidden in production"):
        stub_principal_resolver("test")  # the process environment wins


@pytest.mark.parametrize("env", ["", "development", "staging"])
def test_stub_is_refused_outside_test(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    monkeypatch.setenv("AIP_ENV", env)
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    with pytest.raises(RuntimeError, match="only allowed"):
        create_app(env=env, tracing=False)


def test_no_stub_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.delenv("AUTH_TEST_STUB", raising=False)
    assert stub_principal_resolver("test") is None
    monkeypatch.setenv("AUTH_TEST_STUB", "0")
    assert stub_principal_resolver("test") is None
    with pytest.raises(RuntimeError):
        StubHeaderPrincipalResolver()


async def test_stub_reads_the_header_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    resolver = stub_principal_resolver("test")
    assert resolver is not None

    good = json.dumps(_principal_json())
    p = await resolver.resolve({TEST_PRINCIPAL_HEADER: good})
    assert p is not None and p.user_id == USER_ID
    assert await resolver.resolve({}) is None
    assert await resolver.resolve({TEST_PRINCIPAL_HEADER: "{not json"}) is None
    bad = json.dumps(_principal_json(userClass="admin"))
    assert await resolver.resolve({TEST_PRINCIPAL_HEADER: bad}) is None
    platform = await PlatformPrincipalAdapter(resolver).resolve({TEST_PRINCIPAL_HEADER: good})
    assert platform is not None
    assert platform.tenant_id == TENANT_A_ID and platform.actor_id == USER_ID
    # Turned off after start: the stub stops authenticating at once.
    monkeypatch.setenv("AUTH_TEST_STUB", "0")
    assert await resolver.resolve({TEST_PRINCIPAL_HEADER: good}) is None
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("AIP_ENV", "production")
    assert await resolver.resolve({TEST_PRINCIPAL_HEADER: good}) is None
