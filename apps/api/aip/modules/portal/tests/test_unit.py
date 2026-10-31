"""PORTAL-01 unit tests: the pure lifecycle rules, action registry and request schemas."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from aip.modules.portal import policies
from aip.modules.portal.policies import (
    access_days,
    effective_status,
    expand_actions,
    grant_state,
    register_action_permissions,
    reinstated_status,
    unknown_action_codes,
)
from aip.modules.portal.routes import check_action_codes
from aip.modules.portal.schemas import GrantIn, InviteIn

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
P1 = UUID("00000000-0000-4000-8000-0000000000a1")


def grant(**changes: Any) -> dict[str, Any]:
    return {"expires_at": NOW + timedelta(days=1), "revoked_at": None, **changes}


@pytest.fixture(autouse=True)
def _restore_actions() -> Iterator[None]:
    saved = {k: list(v) for k, v in policies.ACTION_PERMISSIONS.items()}
    yield
    policies.ACTION_PERMISSIONS.clear()
    policies.ACTION_PERMISSIONS.update(saved)


# --- grant_state / effective_status -------------------------------------------------------------


def test_a_grant_expired_one_second_ago_is_expired() -> None:
    assert grant_state(grant(expires_at=NOW - timedelta(seconds=1)), NOW) == "expired"


def test_a_grant_expiring_at_now_is_expired() -> None:
    assert grant_state(grant(expires_at=NOW), NOW) == "expired"


def test_a_grant_expiring_tomorrow_is_live() -> None:
    assert grant_state(grant(), NOW) == "live"


def test_a_revoked_grant_is_revoked_even_before_expiry() -> None:
    assert grant_state(grant(revoked_at=NOW - timedelta(hours=1)), NOW) == "revoked"


def test_an_active_user_whose_only_grant_expired_is_expired() -> None:
    assert effective_status("active", ["expired"]) == "expired"


def test_an_active_user_with_one_live_grant_left_is_active() -> None:
    assert effective_status("active", ["expired", "live"]) == "active"


def test_an_active_user_with_no_grants_is_active() -> None:
    assert effective_status("active", []) == "active"


@pytest.mark.parametrize("stored", ["suspended", "invited"])
def test_suspended_and_invited_show_as_stored(stored: str) -> None:
    assert effective_status(stored, ["expired"]) == stored


def test_reinstated_status_depends_on_a_previous_sign_in() -> None:
    assert reinstated_status(NOW) == "active"
    assert reinstated_status(None) == "invited"


# --- access period ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "days"),
    [(None, 180), (365, 365), (1, 1), (400, 400), (0, 180), (401, 180), ("365", 180), (True, 180)],
)
def test_access_days_is_the_setting_within_1_to_400_else_180(value: object, days: int) -> None:
    assert access_days(value) == days


# --- action registry ----------------------------------------------------------------------------


def test_registering_codes_on_an_unknown_action_raises() -> None:
    with pytest.raises(ValueError, match="countersign"):
        register_action_permissions("countersign", ["x.y"])


def test_a_host_module_adds_its_code_to_sign_off() -> None:
    register_action_permissions("sign_off", ["inspection.client_review.sign"])
    assert expand_actions(["view", "sign_off"]) == {
        "portal.record.view",
        "portal.record.sign_off",
        "inspection.client_review.sign",
    }


def test_each_action_gives_its_portal_code() -> None:
    assert expand_actions(["view", "witness", "download"]) == {
        "portal.record.view",
        "portal.record.witness",
        "portal.report.download",
    }


def test_a_code_missing_from_the_catalogue_fails_app_start() -> None:
    catalogue = {codes[0] for codes in policies.ACTION_PERMISSIONS.values()}
    check_action_codes(catalogue)  # every built-in code known: starts
    register_action_permissions("sign_off", ["inspection.client_review.sign"])
    assert unknown_action_codes(catalogue) == ["inspection.client_review.sign"]
    with pytest.raises(RuntimeError, match=r"inspection\.client_review\.sign"):
        check_action_codes(catalogue)


# --- schemas ------------------------------------------------------------------------------------


def invite_body(**changes: Any) -> dict[str, Any]:
    return {
        "email": "client.a@rio.example",
        "firstName": "Client",
        "lastName": "A",
        "companyName": "Rio",
        "grants": [{"projectId": str(P1), "actions": ["view", "sign_off"]}],
        **changes,
    }


def test_a_valid_invite_body_parses() -> None:
    body = InviteIn.model_validate(invite_body())
    assert body.grants[0].actions == ["view", "sign_off"]


@pytest.mark.parametrize("extra", [{"role": "admin"}, {"expiresAt": "2030-01-01T00:00:00Z"}])
def test_an_invite_with_an_unknown_key_is_refused(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        InviteIn.model_validate(invite_body(**extra))


@pytest.mark.parametrize(
    "actions", [["view", "delete"], ["sign_off"], [], ["view", "view"], ["view"] * 5]
)
def test_invalid_actions_are_refused(actions: list[str]) -> None:
    with pytest.raises(ValidationError):
        GrantIn.model_validate({"projectId": str(P1), "actions": actions})


def test_an_invite_needs_one_to_twenty_grants() -> None:
    with pytest.raises(ValidationError):
        InviteIn.model_validate(invite_body(grants=[]))
    many = [{"projectId": str(P1), "actions": ["view"]}] * 21
    with pytest.raises(ValidationError):
        InviteIn.model_validate(invite_body(grants=many))
