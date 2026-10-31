"""FORMS-10 unit tests: section rules in the template contract, the lint and the evaluator.

No database. The cross-language cases live in ``evaluate-v2.json`` (both runners); these are the
task spec's worked examples. ``avg_dft_ok`` in the spec averages with ``+`` and ``/``, which the
shared allow-list refuses until FORMS-07 adds the forms-only arithmetic extension, so the examples
use the arithmetic-free ``dft_ok`` (every reading at least 250) with the same readings.
"""

from __future__ import annotations

import copy
from typing import Any

from aip.modules.forms.evaluator import evaluate_answers, evaluation_as_json
from aip.modules.forms.lint import is_error, lint_template
from aip.modules.item_types.api import field_types

FIELD_TYPES = frozenset(f.key for f in field_types())


def lint(schema: dict[str, Any]) -> list[Any]:
    return lint_template(schema, field_types=FIELD_TYPES, known_units={"mm"}.__contains__)


def _codes(schema: dict[str, Any]) -> list[str]:
    return [issue.code for issue in lint(schema)]


def _var(key: str) -> dict[str, str]:
    return {"var": f"answers.{key}"}


DFT_OK = {"and": [{">=": [_var("dft_1"), 250]}, {">=": [_var("dft_2"), 250]}]}

COATING_V2: dict[str, Any] = {
    "schemaVersion": 2,
    "sections": [
        {
            "key": "prep",
            "label": "Preparation",
            "fields": [{"key": "surface_prepared", "type": "boolean", "label": "Prepared"}],
        },
        {
            "key": "coating",
            "label": "Coating",
            "visibleIf": {"==": [_var("surface_prepared"), True]},
            "fields": [
                {"key": "dft_1", "type": "decimal", "label": "DFT 1", "required": True},
                {"key": "dft_2", "type": "decimal", "label": "DFT 2", "required": True},
            ],
            "rules": [{"key": "dft_ok", "expr": DFT_OK, "label": "Every DFT must be >= 250"}],
        },
    ],
}


def _coating() -> dict[str, Any]:
    return copy.deepcopy(COATING_V2)


# --- contract ----------------------------------------------------------------------------------


def test_version_1_without_rules_and_version_2_with_rules_are_valid() -> None:
    v1 = _coating()
    v1["schemaVersion"] = 1
    del v1["sections"][1]["rules"]
    assert lint(v1) == []
    assert lint(_coating()) == []


def test_rules_on_version_1_are_refused() -> None:
    v1 = _coating()
    v1["schemaVersion"] = 1
    issues = lint(v1)
    assert [i.code for i in issues] == ["SCHEMA_INVALID"]
    assert issues[0].path == ["sections", 1]


def test_an_unknown_schema_version_is_refused() -> None:
    v3 = _coating()
    v3["schemaVersion"] = 3
    assert _codes(v3) == ["SCHEMA_INVALID"]


def test_a_rule_needs_a_label_or_label_key_and_no_other_keys() -> None:
    no_label = _coating()
    del no_label["sections"][1]["rules"][0]["label"]
    assert _codes(no_label) == ["SCHEMA_INVALID"]

    label_key = _coating()
    rule = label_key["sections"][1]["rules"][0]
    del rule["label"]
    rule["labelKey"] = "forms.rule.dft_ok"
    assert lint(label_key) == []

    extra = _coating()
    extra["sections"][1]["rules"][0]["severity"] = "high"
    assert _codes(extra) == ["SCHEMA_INVALID"]


def test_at_most_twenty_rules_per_section() -> None:
    schema = _coating()
    schema["sections"][1]["rules"] = [
        {"key": f"rule_{n}", "expr": DFT_OK, "label": "x"} for n in range(21)
    ]
    assert _codes(schema) == ["SCHEMA_INVALID"]


def test_duplicate_rule_keys_are_refused() -> None:
    schema = _coating()
    schema["sections"][1]["rules"].append({"key": "dft_ok", "expr": DFT_OK, "label": "again"})
    issues = lint(schema)
    assert [(i.code, i.path) for i in issues] == [
        ("DUPLICATE_KEY", ["sections", 1, "rules", 1, "key"])
    ]


def test_rule_keys_share_the_section_and_field_namespace() -> None:
    clashes_field = _coating()
    clashes_field["sections"][1]["rules"][0]["key"] = "dft_1"
    assert _codes(clashes_field) == ["DUPLICATE_KEY"]

    clashes_section = _coating()
    clashes_section["sections"][1]["rules"][0]["key"] = "prep"
    assert _codes(clashes_section) == ["DUPLICATE_KEY"]


# --- lint --------------------------------------------------------------------------------------


def test_a_rule_reading_a_field_not_in_the_template_is_an_unknown_reference() -> None:
    schema = _coating()
    schema["sections"][1]["rules"][0]["expr"] = {">=": [_var("nozzle_size"), 2]}
    issues = lint(schema)
    assert [(i.code, i.path, i.severity) for i in issues] == [
        ("UNKNOWN_REFERENCE", ["sections", 1, "rules", 0, "expr"], "error")
    ]


def test_a_rule_with_an_operator_outside_the_allow_list_is_invalid() -> None:
    # The spec's average needs arithmetic, which arrives with FORMS-07.
    schema = _coating()
    schema["sections"][1]["rules"][0]["expr"] = {
        ">=": [{"/": [{"+": [_var("dft_1"), _var("dft_2")]}, 2]}, 250]
    }
    issues = lint(schema)
    assert [i.code for i in issues] == ["EXPRESSION_INVALID"]
    assert issues[0].message == "operator not allowed: /"


def test_a_rule_reading_a_hideable_section_is_a_warning_that_does_not_block() -> None:
    schema = _coating()
    schema["sections"].append(
        {
            "key": "summary",
            "label": "Summary",
            "fields": [{"key": "remarks", "type": "text", "label": "Remarks"}],
            "rules": [{"key": "summary_ok", "expr": {">=": [_var("dft_1"), 250]}, "label": "x"}],
        }
    )
    issues = lint(schema)
    assert [(i.code, i.path, i.severity) for i in issues] == [
        ("RULE_READS_HIDDEN_FIELD", ["sections", 2, "rules", 0, "expr"], "warning")
    ]
    assert not any(is_error(i) for i in issues)
    assert issues[0].as_dict()["severity"] == "warning"


def test_a_rule_reading_its_own_section_or_an_always_visible_one_is_clean() -> None:
    schema = _coating()
    schema["sections"][1]["rules"].append(
        {"key": "prepared", "expr": {"==": [_var("surface_prepared"), True]}, "label": "x"}
    )
    assert lint(schema) == []


# --- evaluator (the spec's worked examples) ----------------------------------------------------


def _sections(answers: dict[str, Any]) -> dict[str, Any]:
    result = evaluation_as_json(evaluate_answers(COATING_V2, answers, mode="submit"))
    return result["sections"]


def test_dft_300_300_completes_the_section() -> None:
    coating = _sections({"surface_prepared": True, "dft_1": 300, "dft_2": 300})["coating"]
    assert coating == {
        "visible": True,
        "missingRequired": [],
        "invalid": [],
        "failed": [],
        "ruleFailures": [],
        "complete": True,
    }


def test_dft_200_250_fails_the_rule() -> None:
    result = evaluation_as_json(
        evaluate_answers(
            COATING_V2, {"surface_prepared": True, "dft_1": 200, "dft_2": 250}, mode="submit"
        )
    )
    assert result["sections"]["coating"]["ruleFailures"] == ["dft_ok"]
    assert result["sections"]["coating"]["complete"] is False
    assert result["errors"] == []
    assert result["complete"] is False  # a failed section rule keeps the whole form incomplete


def test_a_hidden_section_does_not_evaluate_its_rule() -> None:
    coating = _sections({"surface_prepared": False, "dft_1": 1, "dft_2": 1})["coating"]
    assert coating["visible"] is False
    assert coating["ruleFailures"] == []
    assert coating["complete"] is False
