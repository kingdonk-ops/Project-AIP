"""ENT-01 unit tests: plans, the pure resolver and limit decisions. No database."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aip.modules.tenancy.entitlements.plans import (
    ADD_ONS,
    PLANS,
    AddOn,
    ContractRefRequiredError,
    Plan,
    build_registry,
    check_contract_ref,
)
from aip.modules.tenancy.entitlements.resolve import (
    InvalidEntitlementKey,
    OverrideView,
    Resolution,
    SubscriptionView,
    decide_limit,
    resolve,
)

NOW = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
TENANT = uuid4()


def subscription(plan: str = "core", **extra: Any) -> SubscriptionView:
    fields: dict[str, Any] = {
        "tenant_id": TENANT,
        "plan_code": plan,
        "plan_version": 1,
        "term": "sandbox",
        "status": "active",
        "starts_on": date(2026, 1, 1),
        **extra,
    }
    return SubscriptionView(**fields)


def override(
    key: str, value: bool | int | None, *, expires_at: datetime | None = None
) -> OverrideView:
    return OverrideView(
        id=uuid4(), key=key, value=value, reason="test", created_at=NOW, expires_at=expires_at
    )


def run(
    key: str,
    *,
    sub: SubscriptionView | None = None,
    plan: Plan | None = None,
    add_ons: Sequence[str] = (),
    overrides: Sequence[OverrideView] = (),
    toggles: Mapping[str, bool] | None = None,
) -> Resolution:
    sub = subscription() if sub is None else sub
    return resolve(
        key,
        subscription=sub,
        plan=PLANS[sub.plan_code] if plan is None else plan,
        add_ons=[ADD_ONS[code] for code in add_ons],
        overrides=overrides,
        toggles=toggles or {},
        now=NOW,
    )


# --- the spec's resolution cases ----------------------------------------------------------------


def test_add_on_switches_a_feature_on() -> None:
    assert PLANS["core"].features["feature.bim"] is False
    assert run("feature.bim", add_ons=["bim"]) == Resolution(True, "add_on")


def test_an_override_beats_the_add_on() -> None:
    result = run("feature.bim", add_ons=["bim"], overrides=[override("feature.bim", False)])
    assert result == Resolution(False, "override")


def test_an_override_that_expired_yesterday_is_ignored() -> None:
    expired = override("feature.bim", False, expires_at=NOW - timedelta(days=1))
    assert run("feature.bim", add_ons=["bim"], overrides=[expired]) == Resolution(True, "add_on")


def test_a_project_toggle_narrows_but_never_grants() -> None:
    off = run("feature.bim", add_ons=["bim"], toggles={"feature.bim": False})
    assert off == Resolution(False, "toggle")
    on = run("feature.bim", toggles={"feature.bim": True})
    assert on == Resolution(False, "plan")


def test_a_toggle_never_changes_a_limit() -> None:
    result = run("limit.projects", toggles={"limit.projects": False})
    assert (result.value, result.source) == (2, "plan")


def test_a_lower_or_higher_override_replaces_the_plan_limit() -> None:
    plan = Plan.model_validate(
        {
            "code": "test",
            "version": 1,
            "features": {},
            "limits": {"limit.seats.staff": {"value": 50}},
        }
    )
    sub = subscription("test")
    result = run(
        "limit.seats.staff", sub=sub, plan=plan, overrides=[override("limit.seats.staff", 80)]
    )
    assert (result.value, result.source) == (80, "override")
    lower = run(
        "limit.seats.staff", sub=sub, plan=plan, overrides=[override("limit.seats.staff", 10)]
    )
    assert (lower.value, lower.source) == (10, "override")


def test_no_subscription_grants_nothing() -> None:
    result = resolve(
        "feature.bim",
        subscription=None,
        plan=None,
        add_ons=[],
        overrides=[],
        toggles={},
        now=NOW,
    )
    assert result == Resolution(False, "none")


@pytest.mark.parametrize(
    "sub",
    [
        subscription("enterprise", status="expired"),
        subscription("enterprise", status="suspended"),
        subscription("enterprise", ends_on=date(2026, 10, 14)),
    ],
)
def test_a_dead_subscription_grants_nothing(sub: SubscriptionView) -> None:
    assert run("feature.sso", sub=sub) == Resolution(False, "none")
    limit = run("limit.projects", sub=sub)
    assert (limit.value, limit.source) == (0, "none")


@pytest.mark.parametrize("key", ["release.new_nav", "bim", "feature.", "limit", "Feature.bim"])
def test_keys_outside_feature_and_limit_are_rejected(key: str) -> None:
    with pytest.raises(InvalidEntitlementKey):
        run(key)


def test_a_negative_limit_fails_the_plan_registry() -> None:
    with pytest.raises(ValidationError):
        build_registry(
            [
                {
                    "code": "bad",
                    "version": 1,
                    "features": {},
                    "limits": {"limit.projects": {"value": -1}},
                }
            ],
            [],
        )


def test_an_add_on_with_a_negative_increment_fails() -> None:
    with pytest.raises(ValidationError):
        AddOn.model_validate({"code": "bad", "increments": {"limit.db_gb": -20}})


# --- the ADR 0008 plan table -----------------------------------------------------------------


def test_core_allows_one_full_seat() -> None:
    assert decide_limit(run("limit.seats.full"), 1).allowed is True
    over = decide_limit(run("limit.seats.full"), 2)
    assert (over.limit, over.recorded) == (1, True)  # OVERAGE: allowed, recorded for the invoice


def test_professional_seats_and_core_projects() -> None:
    pro = subscription("professional")
    assert run("limit.seats.full", sub=pro).value == 5
    assert decide_limit(run("limit.seats.full", sub=pro), 5).recorded is False
    assert decide_limit(run("limit.seats.full", sub=pro), 6).recorded is True
    assert run("limit.projects").value == 2


def test_sso_is_enterprise_only() -> None:
    assert run("feature.sso", sub=subscription("professional")).value is False
    assert run("feature.sso", sub=subscription("enterprise")).value is True


def test_contracted_seats_and_storage_replace_the_plan() -> None:
    sub = subscription("enterprise", seat_limits={"full": 400}, storage_gb=4096)
    assert run("limit.seats.full", sub=sub) == Resolution(400, "plan", "OVERAGE")
    assert run("limit.storage_gb", sub=sub).value == 4096


def test_db_block_add_on_adds_twenty_gb() -> None:
    assert run("limit.db_gb", add_ons=["db_block_20gb"]) == Resolution(25, "add_on", "WARN")


def test_enterprise_unlimited_stays_unlimited() -> None:
    result = run("limit.projects", sub=subscription("enterprise"))
    assert result.value is None
    assert decide_limit(result, 10_000).allowed is True


# --- limit actions (ADR 0023) -----------------------------------------------------------------


def test_block_refuses_over_the_limit() -> None:
    decision = decide_limit(Resolution(50, "plan", "BLOCK"), 51)
    assert (decision.allowed, decision.limit, decision.threshold) == (False, 50, 100)


def test_warn_allows_and_records() -> None:
    decision = decide_limit(Resolution(5, "plan", "WARN"), 6)
    assert (decision.allowed, decision.recorded) == (True, True)


@pytest.mark.parametrize(("total", "threshold"), [(79, None), (80, 80), (95, 95), (100, 100)])
def test_storage_warns_at_80_and_95_percent(total: int, threshold: int | None) -> None:
    decision = decide_limit(Resolution(100, "plan", "BLOCK"), total)
    assert (decision.allowed, decision.threshold) == (True, threshold)


def test_nothing_granted_is_refused() -> None:
    decision = decide_limit(Resolution(0, "none", "BLOCK"), 1)
    assert (decision.allowed, decision.source) == (False, "none")


# --- contract reference (ADR 0017) -----------------------------------------------------------


@pytest.mark.parametrize("term", ["annual", "multi_year"])
def test_production_terms_need_a_contract_ref(term: str) -> None:
    with pytest.raises(ContractRefRequiredError):
        check_contract_ref(term, None)
    with pytest.raises(ContractRefRequiredError):
        check_contract_ref(term, "  ")
    check_contract_ref(term, "C-1001")


@pytest.mark.parametrize("term", ["trial", "sandbox"])
def test_trial_and_sandbox_need_none(term: str) -> None:
    check_contract_ref(term, None)


def test_a_subscription_that_has_not_started_grants_nothing() -> None:
    future = subscription("enterprise", starts_on=date(2027, 1, 1))
    assert run("feature.sso", sub=future) == Resolution(False, "none")
