"""IDENTITY-04 Part D (ADR 0010): ``derive_assurance`` and the sign-off decision, pure."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from aip.modules.identity.assurance import (
    HOLD_POINT_RELEASE,
    SessionFacts,
    SignoffContext,
    decide,
    derive_assurance,
)

NOW = datetime(2026, 10, 18, 10, 0, tzinfo=UTC)
DEVICE = UUID("00000000-0000-4000-8000-0000000000d1")
STEP_UP = "/api/v1/auth/step-up/start?returnTo=/"


def _at(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


@pytest.mark.parametrize(
    ("session", "level", "method"),
    [
        (SessionFacts(aal=2, amr=["pwd", "hwk"], authenticated_at=_at(1)), 2, "passkey"),
        (SessionFacts(aal=2, amr=["pwd", "otp"], authenticated_at=_at(1)), 2, "totp"),
        (SessionFacts(aal=2, amr=["fed", "mfa", "pwd"], authenticated_at=_at(1)), 2, "idp_mfa"),
        (
            SessionFacts(
                aal=1, amr=["pin"], authenticated_at=_at(1), audience="device", device_id=DEVICE
            ),
            2,
            "device_pin",
        ),
        (SessionFacts(aal=1, amr=["fed", "pwd"], authenticated_at=_at(1)), 1, "password"),
    ],
)
def test_derive_assurance(session: SessionFacts, level: int, method: str) -> None:
    assurance = derive_assurance(session)
    assert (assurance.level, assurance.method) == (level, method)
    assert assurance.authenticated_at == session.authenticated_at
    assert assurance.device_id == session.device_id


def test_a_pin_without_a_registered_device_is_only_a_password() -> None:
    session = SessionFacts(aal=1, amr=["pin"], authenticated_at=_at(1), audience="device")
    assert derive_assurance(session).method == "password"


def _ctx(session: SessionFacts, *, aal2_available: bool = True, **kw: bool) -> SignoffContext:
    return SignoffContext(
        session=session, aal2_available=aal2_available, now=NOW, step_up_url=STEP_UP, **kw
    )


PASSKEY = SessionFacts(aal=2, amr=["pwd", "hwk"], authenticated_at=_at(5))


def test_a_fresh_passkey_releases_a_hold_point() -> None:
    d = decide(_ctx(PASSKEY), HOLD_POINT_RELEASE, min_aal=2, max_age_min=10)
    assert d.decision == "allow"
    assert d.assurance.method == "passkey"
    assert d.step_up_url is None


@pytest.mark.parametrize(
    ("minutes", "decision"), [(9 + 59 / 60, "allow"), (10 + 1 / 60, "step_up_required")]
)
def test_freshness_window(minutes: float, decision: str) -> None:
    session = SessionFacts(aal=2, amr=["pwd", "otp"], authenticated_at=_at(minutes))
    d = decide(_ctx(session), "itp.signoff", min_aal=2, max_age_min=10)
    assert d.decision == decision
    if decision == "step_up_required":
        assert d.step_up_url == STEP_UP


def test_password_only_sso_user_with_an_enrolled_passkey_steps_up() -> None:
    session = SessionFacts(aal=1, amr=["fed", "pwd"], authenticated_at=_at(1))
    d = decide(_ctx(session, aal2_available=True), HOLD_POINT_RELEASE, min_aal=2, max_age_min=10)
    assert d.decision == "step_up_required"
    assert d.assurance.method == "password"


def test_without_any_aal2_method_it_needs_a_countersign() -> None:
    session = SessionFacts(aal=1, amr=["fed", "pwd"], authenticated_at=_at(1))
    d = decide(_ctx(session, aal2_available=False), HOLD_POINT_RELEASE, min_aal=2, max_age_min=10)
    assert d.decision == "countersign_required"


def test_a_field_user_on_a_registered_device_with_a_pin() -> None:
    session = SessionFacts(
        aal=1, amr=["pin"], authenticated_at=_at(1), audience="device", device_id=DEVICE
    )
    d = decide(_ctx(session), HOLD_POINT_RELEASE, min_aal=2, max_age_min=10)
    assert d.decision == "allow"
    assert (d.assurance.method, d.assurance.device_id) == ("device_pin", DEVICE)


def test_a_tenant_minimum_of_one_allows_a_password() -> None:
    session = SessionFacts(aal=1, amr=["fed", "pwd"], authenticated_at=_at(1))
    d = decide(_ctx(session), "record.seal", min_aal=1, max_age_min=10)
    assert d.decision == "allow" and d.min_aal == 1


# --- ADR 0010 addendum: a client's PIN-only hold-point signature ---------------------------------

CLIENT_PIN = SessionFacts(
    aal=1, amr=["pin"], authenticated_at=_at(1), audience="device", device_id=DEVICE
)


def test_pin_only_setting_off_needs_the_clients_phone() -> None:
    d = decide(
        _ctx(CLIENT_PIN, client_signature=True), HOLD_POINT_RELEASE, min_aal=2, max_age_min=10
    )
    assert d.decision == "step_up_required"


def test_pin_only_setting_on_allows() -> None:
    ctx = _ctx(CLIENT_PIN, client_signature=True, holdpoint_client_pin_only=True)
    assert decide(ctx, HOLD_POINT_RELEASE, min_aal=2, max_age_min=10).decision == "allow"


def test_pin_only_setting_on_and_offline_is_provisional() -> None:
    ctx = _ctx(CLIENT_PIN, client_signature=True, holdpoint_client_pin_only=True, offline=True)
    assert (
        decide(ctx, HOLD_POINT_RELEASE, min_aal=2, max_age_min=10).decision == "allow_provisional"
    )


def test_pin_only_setting_off_and_offline_does_not_take_effect() -> None:
    ctx = _ctx(CLIENT_PIN, client_signature=True, offline=True)
    assert (
        decide(ctx, HOLD_POINT_RELEASE, min_aal=2, max_age_min=10).decision
        == "countersign_required"
    )
