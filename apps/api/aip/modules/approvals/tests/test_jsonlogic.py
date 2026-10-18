"""APPROVALS-02 Part B: the allow-listed JSONLogic evaluator (pure, no database)."""

from __future__ import annotations

from typing import Any

import pytest

from aip.modules.approvals.guards import jsonlogic
from aip.modules.approvals.guards.jsonlogic import GuardError, evaluate_guard, validate_guard

CLEAN = {"==": [{"var": "record.openCriticalIssues"}, 0]}


def test_a_guard_reads_record_facts() -> None:
    assert evaluate_guard(CLEAN, {"record": {"openCriticalIssues": 0}}) is True
    assert evaluate_guard(CLEAN, {"record": {"openCriticalIssues": 2}}) is False


def test_iteration_operators_are_refused() -> None:
    expr = {"some": [{"var": "record.items"}, {"==": [{"var": ""}, 1]}]}
    with pytest.raises(GuardError, match="operator not allowed: some"):
        validate_guard(expr)


@pytest.mark.parametrize("op", ["all", "none", "map", "reduce", "filter", "merge", "method", "cat"])
def test_every_operator_outside_the_allow_list_is_refused(op: str) -> None:
    with pytest.raises(GuardError, match=f"operator not allowed: {op}"):
        validate_guard({"and": [True, {op: [[1], 1]}]})


def test_an_unknown_operator_is_refused() -> None:
    with pytest.raises(GuardError, match="operator not allowed: exec"):
        validate_guard({"exec": ["rm -rf /"]})


def test_a_guard_nested_too_deep_is_refused() -> None:
    expr: Any = True
    for _ in range(25):
        expr = {"and": [expr]}
    with pytest.raises(GuardError, match="guard too deep"):
        validate_guard(expr)


def test_a_guard_with_too_many_nodes_or_bytes_is_refused() -> None:
    with pytest.raises(GuardError, match="guard too large"):
        validate_guard({"and": [True] * 250})
    with pytest.raises(GuardError, match="guard too large"):
        validate_guard({"in": ["x", "y" * 9000]})


def test_a_guard_must_be_an_operation_with_one_operator() -> None:
    with pytest.raises(GuardError):
        validate_guard(True)
    with pytest.raises(GuardError, match="exactly one operator"):
        validate_guard({"==": [1, 1], "!=": [1, 2]})


def test_evaluation_cannot_change_the_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    def mutate(data: Any, args: list[object]) -> object:
        data["record"]["allPhotosClean"] = True  # the facts are frozen: this raises
        return True

    monkeypatch.setattr(jsonlogic, "ALLOWED_OPERATORS", jsonlogic.ALLOWED_OPERATORS | {"mutate"})
    monkeypatch.setitem(jsonlogic._OPERATIONS, "mutate", mutate)  # pyright: ignore[reportPrivateUsage]
    facts = {"record": {"allPhotosClean": False}}
    with pytest.raises(GuardError):
        evaluate_guard({"mutate": []}, facts)
    assert facts["record"]["allPhotosClean"] is False


def test_the_allow_list_is_restored_after_the_mutation_test() -> None:
    assert "mutate" not in jsonlogic.ALLOWED_OPERATORS
    with pytest.raises(GuardError, match="operator not allowed: mutate"):
        validate_guard({"mutate": []})


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ({"==": [1, "1"]}, True),
        ({"===": [1, "1"]}, False),
        ({"!==": [True, 1]}, True),
        ({"!=": [None, 0]}, True),
        ({"<": [1, 2, 3]}, True),
        ({"<=": [1, 1]}, True),
        ({">": ["b", "a"]}, True),
        ({">=": [1, "x"]}, False),
        ({"!": [[]]}, True),
        ({"!!": ["0"]}, True),
        ({"and": [True, 0, 1]}, 0),
        ({"or": [False, "", "yes"]}, "yes"),
        ({"if": [False, "a", {"var": "record.n"}, "b", "c"]}, "b"),
        ({"in": ["ok", "token"]}, True),
        ({"in": ["no", "token"]}, False),
        ({"in": ["Ok", ["Ok", "Bad"]]}, True),
        ({"var": ["record.missing", 7]}, 7),
        ({"var": "record.list.1"}, 20),
        ({"missing": ["record.n", "record.absent"]}, ["record.absent"]),
        ({"missing_some": [1, ["record.n", "record.absent"]]}, []),
        ({"!": {"var": "record.empty"}}, False),  # every object is truthy, as in JavaScript
        ({"!!": {"var": "record.empty"}}, True),
        ({">": ["inf", 50]}, False),  # Number("inf") is NaN in JavaScript
        ({">": ["1_000", 50]}, False),
        ({">": ["Infinity", 50]}, True),
        ({"==": [" 1e2 ", 100]}, True),
    ],
)
def test_operator_semantics_follow_jsonlogic(expr: dict[str, Any], expected: object) -> None:
    data = {"record": {"n": 3, "list": [10, 20], "empty": {}}}
    assert evaluate_guard(expr, data) == expected
