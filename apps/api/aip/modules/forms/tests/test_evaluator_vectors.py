"""FORMS-02/10: the Python evaluator on the shared golden vectors, plus the acceptance examples.

The three vector files drive both this suite and the Vitest twin
(``packages/form-renderer/src/logic``); a case that one passes and the other fails breaks CI in both
languages. No database here — the evaluator is pure.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from aip.modules.approvals.api import GuardError, evaluate_guard
from aip.modules.forms.evaluator import EVALUATOR_VERSION, evaluate_answers, evaluation_as_json
from aip.modules.forms.lint import is_error, lint_template
from aip.modules.item_types.api import field_types
from aip.modules.terms.api import UnknownUnitError, to_si

_VECTORS = Path(__file__).resolve().parents[6] / "packages/contracts/jsonlogic-vectors/forms"
EXPRESSIONS = json.loads((_VECTORS / "expressions-v1.json").read_text(encoding="utf-8"))
EVALUATE = json.loads((_VECTORS / "evaluate-v1.json").read_text(encoding="utf-8"))
EVALUATE_V2 = json.loads((_VECTORS / "evaluate-v2.json").read_text(encoding="utf-8"))

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
COATING = json.loads((_FIXTURES / "coating-itr-min.json").read_text(encoding="utf-8"))

FIELD_TYPES = {f.key for f in field_types()}


def _known_unit(unit: str) -> bool:
    try:
        to_si(1, unit)
    except UnknownUnitError:
        return False
    return True


def _lint(schema: dict[str, Any]) -> list[Any]:
    return lint_template(schema, field_types=FIELD_TYPES, known_units=_known_unit)


def _plain(value: Any) -> Any:
    if isinstance(value, (MappingProxyType, dict)):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _evaluate(case: dict[str, Any]) -> dict[str, Any]:
    return evaluation_as_json(
        evaluate_answers(
            case["schema"], case["answers"], mode=case["mode"], context=case["context"]
        )
    )


# --- vector shape ------------------------------------------------------------------------------


def test_vector_versions_match_the_evaluator() -> None:
    # The v1 files are frozen at version 1; evaluate-v2 is the evaluator's current version.
    assert str(EXPRESSIONS["version"]) == "1"
    assert str(EVALUATE["version"]) == "1"
    assert str(EVALUATE_V2["version"]) == EVALUATOR_VERSION


def test_vector_counts_meet_the_floor() -> None:
    assert len(EXPRESSIONS["cases"]) >= 80
    assert len(EVALUATE["cases"]) >= 30
    assert len(EVALUATE_V2["cases"]) >= 10
    assert set(EVALUATE_V2["v1Sections"]) == {c["name"] for c in EVALUATE["cases"]}


# --- expression vectors ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case", EXPRESSIONS["cases"], ids=[c["name"] for c in EXPRESSIONS["cases"]]
)
def test_expression_vectors(case: dict[str, Any]) -> None:
    if "error" in case:
        with pytest.raises(GuardError) as exc:
            evaluate_guard(case["expr"], case.get("data", {}))
        assert str(exc.value) == case["error"]
    else:
        assert _plain(evaluate_guard(case["expr"], case["data"])) == case["expected"]


# --- evaluate vectors --------------------------------------------------------------------------


@pytest.mark.parametrize("case", EVALUATE["cases"], ids=[c["name"] for c in EVALUATE["cases"]])
def test_evaluate_vector_schema_lints_clean(case: dict[str, Any]) -> None:
    assert _lint(case["schema"]) == []


@pytest.mark.parametrize("case", EVALUATE["cases"], ids=[c["name"] for c in EVALUATE["cases"]])
def test_evaluate_vectors(case: dict[str, Any]) -> None:
    # A v1 case is unchanged; FORMS-10's per-section result is checked against evaluate-v2.
    result = _evaluate(case)
    sections = result.pop("sections")
    assert result == case["expected"]
    assert sections == EVALUATE_V2["v1Sections"][case["name"]]


@pytest.mark.parametrize(
    "case", EVALUATE_V2["cases"], ids=[c["name"] for c in EVALUATE_V2["cases"]]
)
def test_evaluate_v2_vector_schema_has_no_lint_errors(case: dict[str, Any]) -> None:
    assert [issue for issue in _lint(case["schema"]) if is_error(issue)] == []


@pytest.mark.parametrize(
    "case", EVALUATE_V2["cases"], ids=[c["name"] for c in EVALUATE_V2["cases"]]
)
def test_evaluate_v2_vectors(case: dict[str, Any]) -> None:
    assert _evaluate(case) == case["expected"]


# --- acceptance examples (the task spec's worked cases) ----------------------------------------


def test_required_field_shown_by_condition_is_required_only_in_submit() -> None:
    submit = evaluation_as_json(
        evaluate_answers(COATING, {"surface_prepared": False}, mode="submit")
    )
    assert submit["visible"]["remarks"] is True
    assert submit["required"]["blast_standard"] is True
    assert {"fieldKey": "blast_standard", "code": "REQUIRED"}.items() <= submit["errors"][0].items()
    assert submit["complete"] is False

    draft = evaluation_as_json(evaluate_answers(COATING, {"surface_prepared": False}, mode="draft"))
    assert all(e["code"] != "REQUIRED" for e in draft["errors"])


def test_hidden_field_answer_is_ignored_not_errored() -> None:
    result = evaluation_as_json(
        evaluate_answers(COATING, {"surface_prepared": True, "remarks": "old"}, mode="submit")
    )
    assert result["visible"]["remarks"] is False
    assert result["ignored"] == ["remarks"]
    assert all(e["fieldKey"] != "remarks" for e in result["errors"])


def test_failwhen_on_a_measurement() -> None:
    low = evaluation_as_json(
        evaluate_answers(COATING, {"dft_avg": {"value": 0.18, "unit": "mm"}}, mode="submit")
    )
    assert low["failed"] == ["dft_avg"]
    ok = evaluation_as_json(
        evaluate_answers(COATING, {"dft_avg": {"value": 0.30, "unit": "mm"}}, mode="submit")
    )
    assert ok["failed"] == []
    wrong = evaluation_as_json(
        evaluate_answers(COATING, {"dft_avg": {"value": 0.3, "unit": "in"}}, mode="submit")
    )
    assert any(
        e
        == {
            "fieldKey": "dft_avg",
            "code": "WRONG_TYPE",
            "messageKey": "forms.answer.WRONG_TYPE",
            "params": {},
        }
        for e in wrong["errors"]
    )


def test_not_an_option_and_unknown_field() -> None:
    option = evaluation_as_json(evaluate_answers(COATING, {"blast_standard": "sa4"}, mode="submit"))
    assert any(
        e["fieldKey"] == "blast_standard" and e["code"] == "NOT_AN_OPTION" for e in option["errors"]
    )
    unknown = evaluation_as_json(evaluate_answers(COATING, {"extra": 1}, mode="submit"))
    assert any(
        e
        == {
            "fieldKey": "extra",
            "code": "UNKNOWN_FIELD",
            "messageKey": "forms.answer.UNKNOWN_FIELD",
            "params": {},
        }
        for e in unknown["errors"]
    )


def test_text_length_counts_code_points_and_date_must_be_real() -> None:
    schema = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "s",
                "label": "S",
                "fields": [
                    {
                        "key": "code",
                        "type": "text",
                        "label": "Code",
                        "validations": {"maxLength": 3},
                    },
                    {"key": "when", "type": "date", "label": "When"},
                ],
            }
        ],
    }
    assert _lint(schema) == []
    result = evaluation_as_json(
        evaluate_answers(schema, {"code": "héllo", "when": "2026-02-30"}, mode="submit")
    )
    by_field = {e["fieldKey"]: e for e in result["errors"]}
    assert by_field["code"]["code"] == "TOO_LONG" and by_field["code"]["params"] == {"maxLength": 3}
    assert by_field["when"]["code"] == "WRONG_TYPE"


def test_an_expression_that_raises_fails_closed_to_visible() -> None:
    schema = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "s",
                "label": "S",
                "fields": [
                    {
                        "key": "x",
                        "type": "text",
                        "label": "X",
                        "visibleIf": {"missing_some": ["x", []]},
                    }
                ],
            }
        ],
    }
    assert _lint(schema) == []
    result = evaluation_as_json(evaluate_answers(schema, {"x": "v"}, mode="submit"))
    assert result["visible"]["x"] is True
    assert result["expressionErrors"] == [
        {
            "fieldKey": "x",
            "expression": "visibleIf",
            "message": "missing_some needs [minimum, [keys]]",
        }
    ]
