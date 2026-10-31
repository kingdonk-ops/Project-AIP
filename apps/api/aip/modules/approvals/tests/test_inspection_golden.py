"""APPROVALS-05/09/10: the inspection lifecycle presets and golden cases, through the evaluator.

The same cases run through ``TransitionService`` on Postgres in ``test_inspection_preset_db.py``.
APPROVALS-09 rewrote both presets and the cases to the owner's AIP status and action tables
(``confirmedBy: "owner"``); APPROVALS-10 renamed the tablet state and its actions from Go to
SiteSync (ADR 0041 §1). A cases file without ``confirmedBy`` would warn that it is provisional.
A case with ``"comment": false`` takes its actions without a comment; the evaluator has no comment
rule, so the runner applies the transition service's (422 ``COMMENT_REQUIRED``).
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import pytest

from aip.modules.approvals.engine.evaluator import (
    TransitionRejected,
    apply_transition,
    available_transitions,
)
from aip.modules.approvals.presets import list_presets, load_preset, workflows_dir
from aip.modules.approvals.schemas import WorkflowDefinitionSpec, validate_spec
from aip.platform.db.migrator import repo_root

CASES_FILE = Path(__file__).parent / "golden" / "inspection_lifecycle_cases.json"
PRESET_FOR = {"standard": "inspection_standard", "client_review": "inspection_client_review"}
INSPECTION_PERMISSIONS = frozenset(
    f"approvals.inspection.{verb}"
    for verb in ("assign", "execute", "review", "approve", "client_approve", "retire")
)
PROVISIONAL_WARNING = "PROVISIONAL golden cases — owner confirmation pending"


def golden() -> dict[str, Any]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def golden_cases() -> list[Any]:
    """The cases as pytest params, one per case, with the case name as the id."""
    return [pytest.param(case, id=case["name"]) for case in golden()["cases"]]


def path_to(variant: str, state: str) -> list[str]:
    """The actions that take a new ``variant`` instance from ``draft`` to ``state``."""
    return list(golden()["paths"][variant][state])


def preset_spec(variant: str) -> WorkflowDefinitionSpec:
    return validate_spec(load_preset(PRESET_FOR[variant]).spec)


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Apply the case's actions from its start state; the outcome in the cases' ``expect`` shape."""
    spec = preset_spec(case["variant"])
    state = case["start"]
    for action in case["actions"]:
        outcome = apply_transition(spec, state, action)
        if isinstance(outcome, TransitionRejected):
            return {"error": outcome.error}
        if outcome.transition.requires_comment and not case.get("comment", True):
            return {"error": "COMMENT_REQUIRED"}
        state = outcome.to_state
    if "available" in case["expect"]:
        return {"available": available_transitions(spec, state, INSPECTION_PERMISSIONS)}
    return {"state": state}


def test_the_cases_say_whether_the_owner_confirmed_them() -> None:
    header = golden()
    assert header["source"]
    if header["confirmedBy"] is None:
        warnings.warn(PROVISIONAL_WARNING, UserWarning, stacklevel=1)
    else:
        assert header["confirmedOn"], "a confirmed cases file names the date"


@pytest.mark.parametrize("case", golden_cases())
def test_golden_case_through_the_evaluator(case: dict[str, Any]) -> None:
    assert run_case(case) == case["expect"]


def test_every_case_start_state_has_a_path_from_draft() -> None:
    for case in golden()["cases"]:
        spec = preset_spec(case["variant"])
        state = spec.initial
        for action in path_to(case["variant"], case["start"]):
            outcome = apply_transition(spec, state, action)
            assert not isinstance(outcome, TransitionRejected), (case["name"], action)
            state = outcome.to_state
        assert state == case["start"], case["name"]


def test_both_presets_are_valid_inspection_workflows() -> None:
    presets = {p.key: p for p in list_presets()}
    assert set(PRESET_FOR.values()) <= set(presets)
    for key in PRESET_FOR.values():
        assert presets[key].record_type == "inspection"
        spec = validate_spec(presets[key].spec)  # graph rules: every state is reachable
        assert spec.initial == "draft"
        # Performed and Retired are not terminal: INSPECTIONS-09 adds reinspect and supersede.
        assert [s.code for s in spec.states if s.terminal] == []


def test_the_standard_preset_has_the_owners_eleven_states() -> None:
    assert [s.code for s in preset_spec("standard").states] == [
        "draft",
        "clarification_required",
        "assignable",
        "assigned",
        "in_progress",
        "in_progress_sitesync",
        "inspector_review",
        "supervisor_review",
        "rework_required",
        "performed",
        "retired",
    ]


def test_assignee_pairs_share_a_label_and_split_on_the_target() -> None:
    for variant in PRESET_FOR:
        spec = preset_spec(variant)
        by_key = {(t.from_state, t.action): t for t in spec.transitions}
        twins = [t for t in spec.transitions if t.action.endswith("_unassigned")]
        assert {t.action for t in twins} == {
            f"{a}_unassigned"
            for a in ("ready", "schedule", "assign", "assign_with_comment", "handover")
        }
        for twin in twins:
            pair = by_key[(twin.from_state, twin.action.removesuffix("_unassigned"))]
            assert (pair.to_state, twin.to_state) == ("assigned", "assignable")
            assert twin.label_key == pair.label_key
            assert twin.required_permission == pair.required_permission
            assert twin.requires_comment == pair.requires_comment


def test_client_review_exists_only_in_the_client_variant() -> None:
    standard = {s.code for s in preset_spec("standard").states}
    client = {s.code for s in preset_spec("client_review").states}
    assert client - standard == {"client_review"}


def test_only_the_final_sign_off_is_critical() -> None:
    def critical(variant: str) -> set[tuple[str, str]]:
        return {(t.from_state, t.action) for t in preset_spec(variant).transitions if t.critical}

    assert critical("standard") == {("supervisor_review", "mark_performed")}
    assert critical("client_review") == {("client_review", "client_approve")}


COMMENTED = {
    "request_clarification",
    "request_rework",
    "retire",
    "assign_with_comment",
    "assign_with_comment_unassigned",
}


def test_exactly_the_owners_comment_actions_need_a_comment() -> None:
    for variant in PRESET_FOR:
        transitions = preset_spec(variant).transitions
        assert {t.action for t in transitions if t.requires_comment} == COMMENTED
        assert all(t.requires_comment for t in transitions if t.action in COMMENTED)


def test_retire_has_its_own_permission() -> None:
    for variant in PRESET_FOR:
        transitions = preset_spec(variant).transitions
        retires = {t.required_permission for t in transitions if t.action == "retire"}
        assert retires == {"approvals.inspection.retire"}
        others = {t.required_permission for t in transitions if t.action != "retire"}
        # Inspector Review is the inspector's own desk review now: no transition needs `review`.
        assert "approvals.inspection.retire" not in others
        assert "approvals.inspection.review" not in others


def test_every_transition_uses_an_inspection_permission() -> None:
    for variant in PRESET_FOR:
        used = {t.required_permission for t in preset_spec(variant).transitions}
        assert used <= INSPECTION_PERMISSIONS


def test_every_label_key_is_in_the_en_au_dictionary() -> None:
    # The dictionary files directly: tests may import another module only through its api.
    known: set[str] = set()
    for path in (repo_root() / "config" / "terms" / "en-AU").glob("*.json"):
        known |= set(json.loads(path.read_text(encoding="utf-8")))
    missing: list[str] = []
    for variant in PRESET_FOR:
        spec = preset_spec(variant)
        keys = [s.label_key for s in spec.states] + [t.label_key for t in spec.transitions]
        missing += [key for key in keys if key not in known]
    assert missing == []


GO_CODES = {"in_progress_go": "state", "go_checkout": "action", "check_in": "action"}
SITESYNC_LABELS = {
    "workflow.inspection.state.in_progress_sitesync": "In Progress (SiteSync)",
    "workflow.inspection.action.sitesync_checkout": "SiteSync: Checkout",
    "workflow.inspection.action.sitesync_check_in": "SiteSync: Check In",
}


def test_the_go_codes_are_renamed_to_sitesync() -> None:
    terms = json.loads(
        (repo_root() / "config" / "terms" / "en-AU" / "approvals.json").read_text(encoding="utf-8")
    )
    assert {key: terms[key]["text"] for key in SITESYNC_LABELS} == SITESYNC_LABELS
    removed = {f"workflow.inspection.{kind}.{code}" for code, kind in GO_CODES.items()}
    assert removed.isdisjoint(terms)
    for variant in PRESET_FOR:
        spec = preset_spec(variant)
        codes = {s.code for s in spec.states} | {t.action for t in spec.transitions}
        keys = {s.label_key for s in spec.states} | {t.label_key for t in spec.transitions}
        assert codes.isdisjoint(GO_CODES)
        assert keys.isdisjoint(removed)
        assert {"in_progress_sitesync", "sitesync_checkout", "sitesync_check_in"} <= codes
        assert set(SITESYNC_LABELS) <= keys

def test_the_shipped_presets_live_in_config_workflows() -> None:
    assert workflows_dir() == repo_root() / "config" / "workflows"
