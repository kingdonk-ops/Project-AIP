"""APPROVALS-05: the inspection lifecycle presets and their golden cases, through the pure evaluator.

The same cases run through ``TransitionService`` on Postgres in ``test_inspection_preset_db.py``.
While the cases file has no ``confirmedBy`` they are blueprint-derived and provisional (the AIP
lifecycle tests are not in this repo, OPEN-QUESTIONS #4), and the run says so with a warning.
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
from aip.modules.terms.loader import read_dictionary
from aip.platform.db.migrator import repo_root

CASES_FILE = Path(__file__).parent / "golden" / "inspection_lifecycle_cases.json"
PRESET_FOR = {"standard": "inspection_standard", "client_review": "inspection_client_review"}
INSPECTION_PERMISSIONS = frozenset(
    f"approvals.inspection.{verb}"
    for verb in ("assign", "execute", "review", "approve", "client_approve")
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
        assert [s.code for s in spec.states if s.terminal] == ["completed"]


def test_client_review_exists_only_in_the_client_variant() -> None:
    standard = {s.code for s in preset_spec("standard").states}
    client = {s.code for s in preset_spec("client_review").states}
    assert client - standard == {"client_review"}


def test_only_the_final_sign_off_is_critical() -> None:
    def critical(variant: str) -> set[tuple[str, str]]:
        return {(t.from_state, t.action) for t in preset_spec(variant).transitions if t.critical}

    assert critical("standard") == {("supervisor_review", "approve")}
    assert critical("client_review") == {("client_review", "client_approve")}


def test_every_reject_needs_a_comment() -> None:
    for variant in PRESET_FOR:
        rejects = [t for t in preset_spec(variant).transitions if t.action == "reject"]
        assert rejects
        assert all(t.requires_comment for t in rejects)
        others = [t for t in preset_spec(variant).transitions if t.action != "reject"]
        assert not any(t.requires_comment for t in others)


def test_every_transition_uses_an_inspection_permission() -> None:
    for variant in PRESET_FOR:
        used = {t.required_permission for t in preset_spec(variant).transitions}
        assert used <= INSPECTION_PERMISSIONS


def test_every_label_key_is_in_the_en_au_dictionary() -> None:
    known = {entry.key for entry in read_dictionary(repo_root() / "config" / "terms" / "en-AU")}
    missing: list[str] = []
    for variant in PRESET_FOR:
        spec = preset_spec(variant)
        keys = [s.label_key for s in spec.states] + [t.label_key for t in spec.transitions]
        missing += [key for key in keys if key not in known]
    assert missing == []


def test_the_shipped_presets_live_in_config_workflows() -> None:
    assert workflows_dir() == repo_root() / "config" / "workflows"
