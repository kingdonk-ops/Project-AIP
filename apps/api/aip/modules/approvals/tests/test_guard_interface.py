"""APPROVALS-08: the guard evaluator is reachable through the published interface.

Forms, item_types and issues use the allow-listed JSONLogic through ``aip.modules.approvals.api``
(no deep import into ``guards.jsonlogic``, which import-linter forbids). No database.
"""

from __future__ import annotations

import pytest

from aip.modules.approvals.api import (
    ALLOWED_OPERATORS,
    GuardError,
    evaluate_guard,
    truthy,
    validate_guard,
)


def test_allowed_operators_is_the_shared_set() -> None:
    assert {"==", "!=", "and", "or", "var", "in"} <= ALLOWED_OPERATORS


def test_validate_guard_accepts_an_allowed_operation() -> None:
    validate_guard({"==": [{"var": "x"}, 1]})  # does not raise


@pytest.mark.parametrize("expr", [{"system": [1]}, {"exec": []}, "not an object", 3])
def test_validate_guard_rejects_disallowed_or_non_object(expr: object) -> None:
    with pytest.raises(GuardError):
        validate_guard(expr)


def test_evaluate_guard_reads_record_facts() -> None:
    assert evaluate_guard({"==": [{"var": "x"}, 1]}, {"x": 1}) is True
    assert evaluate_guard({"==": [{"var": "x"}, 1]}, {"x": 2}) is False


def test_truthy_matches_jsonlogic_rules() -> None:
    assert truthy([1]) is True
    assert truthy([]) is False
    assert truthy("ok") is True
    assert truthy(0) is False
    assert truthy(None) is False
