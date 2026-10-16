"""APPROVALS-01: the spec validator and the pure state-machine evaluator (unit, no database)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from aip.modules.approvals.engine.evaluator import (
    TransitionApplied,
    TransitionRejected,
    apply_transition,
    available_transitions,
)
from aip.modules.approvals.schemas import WorkflowDefinitionSpec, validate_spec
from aip.modules.approvals.tests.fixtures import demo_spec, transition

DEMO = validate_spec(demo_spec())


def issues(data: dict[str, Any]) -> list[tuple[tuple[int | str, ...], str]]:
    with pytest.raises(ValidationError) as caught:
        validate_spec(data)
    return [(tuple(e["loc"]), e["msg"]) for e in caught.value.errors()]


# --- evaluator --------------------------------------------------------------------------------


def test_available_transitions_filter_by_state_and_permission() -> None:
    assert available_transitions(DEMO, "draft", frozenset({"approvals.demo.submit"})) == ["submit"]
    assert available_transitions(DEMO, "draft", frozenset()) == []
    assert available_transitions(
        DEMO, "submitted", frozenset({"approvals.demo.approve", "approvals.demo.reject"})
    ) == ["approve", "reject"]
    assert available_transitions(DEMO, "approved", frozenset({"approvals.demo.submit"})) == []
    assert available_transitions(DEMO, "nowhere", frozenset({"approvals.demo.submit"})) == []


def test_apply_transition_rejects_an_action_not_allowed_from_the_state() -> None:
    assert apply_transition(DEMO, "draft", "approve") == TransitionRejected("INVALID_TRANSITION")


def test_apply_transition_moves_to_the_target_state() -> None:
    result = apply_transition(DEMO, "submitted", "approve")
    assert isinstance(result, TransitionApplied)
    assert (result.ok, result.from_state, result.to_state) == (True, "submitted", "approved")
    assert result.transition.action == "approve"
    assert result.transition.critical is True


def test_apply_transition_rejects_an_unknown_state() -> None:
    assert apply_transition(DEMO, "archived", "submit") == TransitionRejected("UNKNOWN_STATE")
    assert TransitionRejected("UNKNOWN_STATE").ok is False


def test_the_evaluator_imports_nothing_from_the_platform() -> None:
    source = (Path(__file__).parents[1] / "engine" / "evaluator.py").read_text(encoding="utf-8")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert imported, "expected some imports"
    assert all(not m.startswith(("aip.platform", "sqlalchemy")) for m in imported), imported
    assert {m for m in imported if m.startswith("aip.")} <= {"aip.modules.approvals.schemas"}


# --- spec validation --------------------------------------------------------------------------


def test_the_demo_spec_is_valid_and_keeps_its_guard_unevaluated() -> None:
    data = demo_spec()
    data["transitions"][0]["guard"] = {"==": [{"var": "record.kind"}, "x"]}
    spec = validate_spec(data)
    assert isinstance(spec, WorkflowDefinitionSpec)
    assert spec.transitions[0].guard == {"==": [{"var": "record.kind"}, "x"]}
    assert spec.model_dump(by_alias=True)["transitions"][0]["from"] == "draft"


def test_an_undeclared_target_state_is_an_issue_at_its_path() -> None:
    data = demo_spec()
    data["transitions"][0]["to"] = "archived"
    found = issues(data)
    assert found[0][0] == ("transitions", 0, "to")
    assert "archived" in found[0][1]


def test_an_undeclared_initial_or_source_state_is_an_issue_at_its_path() -> None:
    data = demo_spec()
    data["initial"] = "nope"
    data["transitions"][1]["from"] = "ghost"
    locs = [loc for loc, _ in issues(data)]
    assert ("initial",) in locs
    assert ("transitions", 1, "from") in locs


def test_an_unreachable_state_is_rejected() -> None:
    data = demo_spec()
    data["states"].append({"code": "orphan", "labelKey": "approvals.demo.state.orphan"})
    found = issues(data)
    assert found == [(("states", 4, "code"), "unreachable state: orphan")]


def test_a_label_must_be_a_term_key_not_display_text() -> None:
    data = demo_spec()
    data["states"][0]["labelKey"] = "Draft"
    assert issues(data)[0][0] == ("states", 0, "labelKey")


def test_a_terminal_state_cannot_have_an_outgoing_transition() -> None:
    data = demo_spec()
    data["transitions"].append(transition("reopen", "approved", "draft"))
    found = issues(data)
    assert found[0][0] == ("transitions", 4, "from")
    assert "terminal" in found[0][1]


def test_from_and_action_must_be_unique() -> None:
    data = demo_spec()
    data["transitions"].append(transition("submit", "draft", "rejected"))
    assert issues(data)[0][0] == ("transitions", 4, "action")


def test_state_codes_must_be_unique() -> None:
    data = demo_spec()
    data["states"].append({"code": "draft", "labelKey": "approvals.demo.state.draft"})
    assert issues(data)[0][0] == ("states", 4, "code")


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("states", 0, "code"), "Draft"),
        (("transitions", 0, "action"), "submit-now"),
        (("transitions", 0, "requiredPermission"), ""),
    ],
)
def test_codes_and_actions_are_snake_case(path: tuple[str, int, str], value: str) -> None:
    data = demo_spec()
    data[path[0]][path[1]][path[2]] = value
    assert issues(data)[0][0] == path


def test_unknown_fields_are_rejected() -> None:
    data = demo_spec()
    data["transitions"][0]["required_role"] = "x"
    assert issues(data)[0][0] == ("transitions", 0, "required_role")


# --- property: the evaluator never leaves the declared states ----------------------------------

_ACTIONS = ("go", "back", "skip", "stop")


@st.composite
def specs(draw: st.DrawFn) -> WorkflowDefinitionSpec:
    """A valid spec: a chain s0 -> s1 -> ... (so all reachable) plus random extra edges."""
    n = draw(st.integers(min_value=1, max_value=6))
    codes = [f"s{i}" for i in range(n)]
    edges: dict[tuple[str, str], str] = {}
    for i in range(n - 1):
        edges[(codes[i], "go")] = codes[i + 1]
    for _ in range(draw(st.integers(min_value=0, max_value=10))):
        src = draw(st.sampled_from(codes))
        action = draw(st.sampled_from(_ACTIONS))
        edges.setdefault((src, action), draw(st.sampled_from(codes)))
    sources = {src for src, _ in edges}
    terminal = {c for c in codes if c not in sources and draw(st.booleans())}
    data = {
        "states": [
            {"code": c, "labelKey": f"t.state.{c}", **({"terminal": True} if c in terminal else {})}
            for c in codes
        ],
        "initial": codes[0],
        "transitions": [transition(a, s, t) for (s, a), t in edges.items()],
    }
    return validate_spec(data)


@settings(max_examples=200, deadline=None)
@given(spec=specs(), steps=st.lists(st.sampled_from((*_ACTIONS, "bogus")), max_size=20))
def test_apply_transition_never_returns_an_undeclared_state(
    spec: WorkflowDefinitionSpec, steps: list[str]
) -> None:
    declared = {s.code for s in spec.states}
    state = spec.initial
    for action in steps:
        result = apply_transition(spec, state, action)
        if isinstance(result, TransitionApplied):
            assert result.to_state in declared
            assert result.from_state == state
            state = result.to_state
        else:
            assert result.error == "INVALID_TRANSITION"
