"""Unit tests for the shared field-type registry and its exported contract (ITEMTYPES-01).

No database: the registry is pure data and ``value_schema`` is a pure function. The config schemas
are checked with the same Draft 2020-12 validator the platform uses for stored schemas.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from aip.modules.item_types.field_types import field_types, get_field_type

REPO_ROOT = Path(__file__).resolve().parents[6]
CONTRACT = REPO_ROOT / "packages" / "contracts" / "field-types" / "field-types.json"

EXPECTED_ORDER = [
    "text",
    "number",
    "decimal",
    "date",
    "dropdown",
    "multi_select",
    "measurement",
    "boolean",
    "photo",
    "signature",
    "asset_ref",
    "user_ref",
]


def test_registry_order() -> None:
    assert [f.key for f in field_types()] == EXPECTED_ORDER


def test_dropdown_value_schema() -> None:
    options = [
        {"value": "cs", "label": "Carbon steel"},
        {"value": "ss", "label": "Stainless"},
    ]
    assert get_field_type("dropdown").value_schema({"options": options}) == {  # type: ignore[union-attr]
        "type": "string",
        "enum": ["cs", "ss"],
    }


def test_measurement_value_schema() -> None:
    assert get_field_type("measurement").value_schema({"unit": "mm", "min": 0, "max": 50}) == {  # type: ignore[union-attr]
        "type": "number",
        "minimum": 0,
        "maximum": 50,
    }


def test_number_default_value_schema() -> None:
    assert get_field_type("number").value_schema({}) == {"type": "integer"}  # type: ignore[union-attr]


def test_unknown_key_is_none() -> None:
    assert get_field_type("gps") is None


def test_text_default_max_length() -> None:
    assert get_field_type("text").value_schema({})["maxLength"] == 2000  # type: ignore[union-attr]


def test_photo_is_form_only() -> None:
    assert "photo" not in [f.key for f in field_types() if "attribute" in f.usable_in]
    assert get_field_type("photo").usable_in == frozenset({"form"})  # type: ignore[union-attr]


def test_every_config_schema_is_valid_draft_2020_12() -> None:
    for field in field_types():
        Draft202012Validator.check_schema(field.config_schema)


@pytest.mark.parametrize(
    ("key", "config", "ok"),
    [
        ("measurement", {"unit": "furlong"}, False),  # not an SI unit
        ("measurement", {"unit": "in"}, False),  # a display unit, not storage
        ("measurement", {"unit": "mm"}, True),
        ("dropdown", {}, False),  # options is required
        ("text", {"colour": "red"}, False),  # additional property
        ("text", {"maxLength": 50}, True),
    ],
)
def test_config_schema_accepts_and_rejects(key: str, config: dict[str, Any], ok: bool) -> None:
    validator = Draft202012Validator(get_field_type(key).config_schema)  # type: ignore[union-attr]
    assert validator.is_valid(config) is ok


def test_exported_contract_matches_generator() -> None:
    """Running the generator into a temp file reproduces the committed contract byte for byte."""
    spec = importlib.util.spec_from_file_location(
        "export_field_types", REPO_ROOT / "tools" / "codegen" / "export_field_types.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.render() == CONTRACT.read_text(encoding="utf-8")
