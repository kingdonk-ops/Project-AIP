"""FORMS-01 lint unit tests: no database. ``field_types`` and ``known_units`` are passed in, so the
checks run standalone. The ``coating-itr-min`` fixture is the golden valid template.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from aip.modules.forms.lint import lint_template
from aip.modules.forms.service import _canonical_hash  # pyright: ignore[reportPrivateUsage]
from aip.modules.item_types.api import field_types

FIELD_TYPES = frozenset(f.key for f in field_types())
KNOWN_UNITS = {"mm", "bar", "degC"}
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "coating-itr-min.json"


def _coating() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def lint(schema: dict[str, Any]) -> list[Any]:
    return lint_template(schema, field_types=FIELD_TYPES, known_units=KNOWN_UNITS.__contains__)


def _codes(schema: dict[str, Any]) -> list[str]:
    return [issue.code for issue in lint(schema)]


def _wrap(*fields: dict[str, Any]) -> dict[str, Any]:
    return {"schemaVersion": 1, "sections": [{"key": "s", "label": "S", "fields": list(fields)}]}


def _field(key: str, type_: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "type": type_, "label": key.title(), **extra}


def test_the_coating_fixture_is_valid() -> None:
    assert lint(_coating()) == []


def test_a_repeated_field_key_is_one_duplicate_key_at_the_second_occurrence() -> None:
    schema = _coating()
    schema["sections"][1]["fields"][2] = _field("dft_avg", "measurement", unit="mm")
    issues = lint(schema)
    assert len(issues) == 1
    assert issues[0].code == "DUPLICATE_KEY"
    assert issues[0].path == ["sections", 1, "fields", 2, "key"]


def test_an_unknown_field_type() -> None:
    assert _codes(_wrap(_field("x", "barcode"))) == ["UNKNOWN_FIELD_TYPE"]


def test_a_dropdown_without_options_and_options_on_a_text() -> None:
    assert _codes(_wrap(_field("choice", "dropdown"))) == ["OPTIONS_REQUIRED"]
    opts = [{"value": "a", "label": "A"}]
    assert _codes(_wrap(_field("note", "text", options=opts))) == ["OPTIONS_NOT_ALLOWED"]


def test_a_measurement_with_an_unknown_unit() -> None:
    assert _codes(_wrap(_field("len", "measurement", unit="furlong"))) == ["UNKNOWN_UNIT"]


def test_validation_range_and_not_allowed() -> None:
    assert _codes(_wrap(_field("n", "number", validations={"min": 5, "max": 1}))) == [
        "VALIDATION_RANGE"
    ]
    assert _codes(_wrap(_field("n", "number", validations={"minLength": 3}))) == [
        "VALIDATION_NOT_ALLOWED"
    ]


def test_a_disallowed_operator_is_expression_invalid_with_the_guard_message() -> None:
    schema = _wrap(_field("a", "boolean", visibleIf={"reduce": [[1], {"+": [1, 1]}, 0]}))
    issues = lint(schema)
    assert len(issues) == 1
    assert issues[0].code == "EXPRESSION_INVALID"
    assert issues[0].message == "operator not allowed: reduce"


def test_a_guard_nested_too_deep_is_expression_invalid() -> None:
    expr: dict[str, Any] = {"var": "answers.a"}
    for _ in range(25):
        expr = {"and": [expr]}
    issues = lint(_wrap(_field("a", "boolean", visibleIf=expr)))
    assert [i.code for i in issues] == ["EXPRESSION_INVALID"]
    assert issues[0].message == "guard too deep"


def test_an_unknown_answer_or_context_reference() -> None:
    assert _codes(_wrap(_field("a", "boolean", visibleIf={"var": "answers.nope"}))) == [
        "UNKNOWN_REFERENCE"
    ]
    assert _codes(_wrap(_field("a", "boolean", visibleIf={"var": "context.userEmail"}))) == [
        "UNKNOWN_REFERENCE"
    ]


def test_a_cycle_between_two_fields_but_not_a_self_referencing_failwhen() -> None:
    cyclic = _wrap(
        _field("a", "boolean", visibleIf={"==": [{"var": "answers.b"}, True]}),
        _field("b", "boolean", requiredIf={"==": [{"var": "answers.a"}, True]}),
    )
    assert _codes(cyclic) == ["CONDITION_CYCLE"]

    self_fail = _wrap(_field("a", "number", failWhen={"<": [{"var": "answers.a"}, 1]}))
    assert lint(self_fail) == []


def test_schema_errors_are_reported_alone_with_a_path() -> None:
    with_extra = _coating()
    with_extra["script"] = "evil"
    issues = lint(with_extra)
    assert [i.code for i in issues] == ["SCHEMA_INVALID"]
    assert issues[0].path == ["script"]

    wrong_version = _coating()
    wrong_version["schemaVersion"] = 2
    assert _codes(wrong_version) == ["SCHEMA_INVALID"]


def test_the_canonical_hash_ignores_key_order_but_not_values() -> None:
    schema = _coating()
    reordered = copy.deepcopy(schema)
    first = reordered["sections"][0]["fields"][0]
    reordered["sections"][0]["fields"][0] = {k: first[k] for k in reversed(list(first))}
    assert _canonical_hash(schema) == _canonical_hash(reordered)

    relabelled = copy.deepcopy(schema)
    relabelled["sections"][0]["label"] = "Different"
    assert _canonical_hash(schema) != _canonical_hash(relabelled)
