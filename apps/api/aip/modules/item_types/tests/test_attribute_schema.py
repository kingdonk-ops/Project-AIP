"""ITEMTYPES-02 unit tests: attribute-definition lint and the compiled per-version JSON Schema.

Pure functions, no database. The compiled schema is checked with the platform's
``validate_attributes`` exactly as ``ItemTypesApi.validate_attributes`` uses it.
"""

from __future__ import annotations

from typing import Any

from aip.modules.item_types.attribute_schema import (
    MAX_ATTRIBUTES,
    compile_schema,
    lint_attributes,
)
from aip.platform.db.jsonb_schema import validate_attributes

WALL_THICKNESS: dict[str, Any] = {
    "key": "wall_thickness",
    "label": "Wall thickness",
    "fieldType": "measurement",
    "required": True,
    "config": {"unit": "mm", "min": 0, "max": 100},
}

COMPILED: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {"wall_thickness": {"type": "number", "minimum": 0, "maximum": 100}},
    "required": ["wall_thickness"],
}


def _attr(key: str, field_type: str = "text", **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": key.title(), "fieldType": field_type, **extra}


def test_a_valid_measurement_attribute_lints_clean() -> None:
    assert lint_attributes([WALL_THICKNESS]) == []


def test_compile_schema_builds_the_draft_2020_12_object_schema() -> None:
    assert compile_schema([WALL_THICKNESS]) == COMPILED


def test_compile_schema_lists_required_keys_in_display_order() -> None:
    attributes = [_attr("b", required=True), _attr("a"), _attr("c", required=True)]
    assert compile_schema(attributes)["required"] == ["b", "c"]
    assert compile_schema([])["required"] == []


def test_a_duplicate_key_is_reported_on_the_second_occurrence() -> None:
    issues = lint_attributes([_attr("material"), _attr("material")])
    assert issues == [("attributes[1].key", "ATTRIBUTE_KEY_DUPLICATE")]


def test_a_key_that_is_not_snake_case_is_invalid() -> None:
    issues = lint_attributes([{"key": "Material", "label": "x", "fieldType": "text"}])
    assert issues == [("attributes[0].key", "ATTRIBUTE_KEY_INVALID")]


def test_a_missing_or_blank_label_is_reported() -> None:
    issues = lint_attributes([{"key": "a", "fieldType": "text"}, {**_attr("b"), "label": " "}])
    assert issues == [
        ("attributes[0].label", "ATTRIBUTE_LABEL_MISSING"),
        ("attributes[1].label", "ATTRIBUTE_LABEL_MISSING"),
    ]


def test_unknown_and_form_only_field_types_are_rejected() -> None:
    assert lint_attributes([_attr("location", "gps")]) == [
        ("attributes[0].fieldType", "ATTRIBUTE_FIELD_TYPE_UNKNOWN")
    ]
    assert lint_attributes([_attr("picture", "photo")]) == [
        ("attributes[0].fieldType", "ATTRIBUTE_FIELD_TYPE_NOT_ALLOWED")
    ]


def test_a_config_that_fails_the_field_types_config_schema_is_invalid() -> None:
    issues = lint_attributes([_attr("thickness", "measurement", config={"unit": "in"})])
    assert issues == [("attributes[0].config", "ATTRIBUTE_CONFIG_INVALID")]


def test_a_missing_required_config_is_invalid() -> None:
    issues = lint_attributes([_attr("thickness", "measurement")])
    assert issues == [("attributes[0].config", "ATTRIBUTE_CONFIG_INVALID")]


def test_min_above_max_is_a_range_error() -> None:
    config = {"unit": "mm", "min": 10, "max": 5}
    issues = lint_attributes([_attr("thickness", "measurement", config=config)])
    assert issues == [("attributes[0].config", "ATTRIBUTE_RANGE_INVALID")]


def test_duplicate_option_values_are_reported_on_the_repeat() -> None:
    options = [{"value": "cs", "label": "Carbon steel"}, {"value": "cs", "label": "Again"}]
    issues = lint_attributes([_attr("material", "dropdown", config={"options": options})])
    assert issues == [("attributes[0].config.options[1].value", "ATTRIBUTE_OPTION_DUPLICATE")]


def test_more_than_the_maximum_attributes_is_one_issue_on_the_list() -> None:
    attributes = [_attr(f"a{i}") for i in range(MAX_ATTRIBUTES + 1)]
    assert MAX_ATTRIBUTES == 200
    assert lint_attributes(attributes) == [("attributes", "ATTRIBUTES_TOO_MANY")]
    assert lint_attributes(attributes[:MAX_ATTRIBUTES]) == []


def test_issues_carry_a_term_key_per_code() -> None:
    issue = lint_attributes([_attr("location", "gps")])[0]
    assert issue.as_dict() == {"path": "attributes[0].fieldType", "code": issue.code}
    assert issue.term_key == "item_types.issue.attribute_field_type_unknown"


def test_the_compiled_schema_rejects_out_of_range_missing_and_extra_values() -> None:
    too_big = validate_attributes(COMPILED, {"wall_thickness": 120})
    assert [(e.path, e.term_key, e.params) for e in too_big] == [
        ("$.wall_thickness", "validation.attribute.maximum", {"limit": 100})
    ]

    missing = validate_attributes(COMPILED, {})
    assert [(e.path, e.term_key) for e in missing] == [
        ("$.wall_thickness", "validation.attribute.required")
    ]

    extra = validate_attributes(COMPILED, {"wall_thickness": 5, "colour": "red"})
    assert [e.term_key for e in extra] == ["validation.attribute.additionalProperties"]
