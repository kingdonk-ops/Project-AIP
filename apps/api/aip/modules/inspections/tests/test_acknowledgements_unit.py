"""INSPECTIONS-10 unit tests: the lock rule, the submit guards in both presets, which submit a
record offers, and the strict acknowledgement body. No database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from aip.modules.approvals.api import evaluate_guard, list_presets, truthy
from aip.modules.inspections.acknowledgements import REPORT, locked_scopes
from aip.modules.inspections.policies import SUBMIT_REPORT, SUBMIT_TO_SUPERVISOR, hidden_submit
from aip.modules.inspections.schemas import AcknowledgementIn

T0 = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
ALICE = "alice"


def row(scope: str, key: str | None, action: str, minutes: int) -> dict[str, Any]:
    return {
        "scope": scope,
        "section_key": key,
        "action": action,
        "actor": ALICE,
        "acted_at": T0 + timedelta(minutes=minutes),
    }


# --- the lock rule ----------------------------------------------------------------------------


def test_a_scope_is_locked_when_its_latest_row_is_a_tick() -> None:
    latest = [
        row("section", "prep", "tick", 1),
        row("section", "coating", "untick", 2),
        row("section", "final", "cleared_by_rework", 3),
        row("report", None, "tick", 4),
    ]
    locks = locked_scopes(latest, None)
    assert set(locks) == {("section", "prep"), REPORT}
    assert locks[("section", "prep")]["actor"] == ALICE


def test_ticks_before_the_last_rework_entry_count_as_cleared() -> None:
    latest = [row("section", "prep", "tick", 1), row("section", "coating", "tick", 10)]
    rework_at = T0 + timedelta(minutes=5)
    assert set(locked_scopes(latest, rework_at)) == {("section", "coating")}
    assert locked_scopes(latest, T0 + timedelta(minutes=20)) == {}


def test_nothing_acknowledged_is_nothing_locked() -> None:
    assert locked_scopes([], None) == {}


# --- the submit guards in both presets ----------------------------------------------------------

SUBMIT_STATES = {
    SUBMIT_TO_SUPERVISOR: {
        "assigned",
        "in_progress",
        "in_progress_sitesync",
        "inspector_review",
        "rework_required",
    },
    SUBMIT_REPORT: {"in_progress", "in_progress_sitesync", "inspector_review"},
}
PRESETS = {p.key: p for p in list_presets()}
SUBMIT_TO = {"inspection_standard": "performed", "inspection_client_review": "client_review"}


def submits(preset: str) -> list[dict[str, Any]]:
    transitions: list[dict[str, Any]] = PRESETS[preset].spec["transitions"]
    return [t for t in transitions if t["action"] in SUBMIT_STATES]


def passes(transition: dict[str, Any], **record: Any) -> bool:
    return truthy(evaluate_guard(transition["guard"], {"record": record}))


@pytest.mark.parametrize("preset", sorted(SUBMIT_TO))
def test_each_preset_has_both_submits_from_the_owners_states(preset: str) -> None:
    found = submits(preset)
    for action, states in SUBMIT_STATES.items():
        assert {t["from"] for t in found if t["action"] == action} == states
    for t in found:
        assert t["guardMessageKey"] == "inspection.guard.submit_not_ready"
    report = [t for t in found if t["action"] == SUBMIT_REPORT]
    assert {t["to"] for t in report} == {SUBMIT_TO[preset]}
    for t in report:  # the doer's critical sign-off, not a supervisor's approval
        assert t["requiredPermission"] == "approvals.inspection.execute"
        assert t["critical"] is True
        assert t["signoffAction"] == "inspection.submit_report"


@pytest.mark.parametrize("preset", sorted(SUBMIT_TO))
@pytest.mark.parametrize("has_review", [True, False])
@pytest.mark.parametrize("acknowledged", [True, False])
@pytest.mark.parametrize("open_steps", [0, 1])
def test_a_submit_passes_only_for_its_setting_with_the_report_ticked(
    preset: str, has_review: bool, acknowledged: bool, open_steps: int
) -> None:
    facts = {
        "hasSupervisorReview": has_review,
        "reportAcknowledged": acknowledged,
        "openStepCount": open_steps,
    }
    ready = acknowledged and open_steps == 0
    for t in submits(preset):
        wants_review = t["action"] == SUBMIT_TO_SUPERVISOR
        assert passes(t, **facts) is (ready and has_review == wants_review), (
            t["from"],
            t["action"],
        )


def test_a_record_hides_the_submit_its_setting_rules_out() -> None:
    assert hidden_submit(True) == SUBMIT_REPORT
    assert hidden_submit(False) == SUBMIT_TO_SUPERVISOR


# --- strict bodies --------------------------------------------------------------------------------


def test_an_acknowledgement_body_takes_no_keys() -> None:
    assert AcknowledgementIn.model_validate({}) == AcknowledgementIn()
    with pytest.raises(ValidationError):
        AcknowledgementIn.model_validate({"actor": "someone"})
