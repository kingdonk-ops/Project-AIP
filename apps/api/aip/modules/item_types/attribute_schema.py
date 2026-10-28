"""Item-type attribute definitions: lint and compile to JSON Schema (ITEMTYPES-02). Pure functions.

An attribute definition is ``{key, label, fieldType, required?, config?, helpText?}``; a version's
``attributes`` is a list of them in display order. ``lint_attributes`` reports every problem as a
``(path, code)`` issue (paths like ``attributes[2].config.unit``); the client renders each code
through the term key ``item_types.issue.<code lower-case>``. ``compile_schema`` turns a lint-clean
list into the Draft 2020-12 schema that ``aip.platform.db.jsonb_schema.validate_attributes`` checks
asset attributes against, using each field type's ``value_schema`` from the one registry.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final, NamedTuple

from jsonschema import Draft202012Validator

from aip.modules.item_types.field_types import get_field_type

__all__ = [
    "MAX_ATTRIBUTES",
    "AttributeDefinitionIssue",
    "compile_schema",
    "lint_attributes",
]

MAX_ATTRIBUTES: Final = 200

_DRAFT: Final = "https://json-schema.org/draft/2020-12/schema"
_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_ATTRIBUTE: Final = "attribute"


class AttributeDefinitionIssue(NamedTuple):
    """One problem in an attribute list: where it is and a stable code."""

    path: str
    code: str

    @property
    def term_key(self) -> str:
        return f"item_types.issue.{self.code.lower()}"

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code}


def _lint_config(at: str, field_key: str, config: Any) -> list[AttributeDefinitionIssue]:
    field = get_field_type(field_key)
    assert field is not None  # the caller checked the field type first
    if not isinstance(config, dict) or not Draft202012Validator(field.config_schema).is_valid(
        config
    ):
        return [AttributeDefinitionIssue(f"{at}.config", "ATTRIBUTE_CONFIG_INVALID")]
    issues: list[AttributeDefinitionIssue] = []
    if "min" in config and "max" in config and config["min"] > config["max"]:
        issues.append(AttributeDefinitionIssue(f"{at}.config", "ATTRIBUTE_RANGE_INVALID"))
    seen: set[str] = set()
    for i, option in enumerate(config.get("options", [])):
        if option["value"] in seen:
            issues.append(
                AttributeDefinitionIssue(
                    f"{at}.config.options[{i}].value", "ATTRIBUTE_OPTION_DUPLICATE"
                )
            )
        seen.add(option["value"])
    return issues


def lint_attributes(attributes: Sequence[dict[str, Any]]) -> list[AttributeDefinitionIssue]:
    """Every problem in ``attributes``, in list order; empty when it can be compiled."""
    if len(attributes) > MAX_ATTRIBUTES:
        return [AttributeDefinitionIssue("attributes", "ATTRIBUTES_TOO_MANY")]
    issues: list[AttributeDefinitionIssue] = []
    keys: set[str] = set()
    for i, attribute in enumerate(attributes):
        at = f"attributes[{i}]"
        key = attribute.get("key")
        if not isinstance(key, str) or not _KEY_RE.match(key):
            issues.append(AttributeDefinitionIssue(f"{at}.key", "ATTRIBUTE_KEY_INVALID"))
        elif key in keys:
            issues.append(AttributeDefinitionIssue(f"{at}.key", "ATTRIBUTE_KEY_DUPLICATE"))
        else:
            keys.add(key)

        label = attribute.get("label")
        if not isinstance(label, str) or not label.strip():
            issues.append(AttributeDefinitionIssue(f"{at}.label", "ATTRIBUTE_LABEL_MISSING"))

        field_key = attribute.get("fieldType")
        field = get_field_type(field_key) if isinstance(field_key, str) else None
        if field is None:
            issues.append(
                AttributeDefinitionIssue(f"{at}.fieldType", "ATTRIBUTE_FIELD_TYPE_UNKNOWN")
            )
        elif _ATTRIBUTE not in field.usable_in:
            issues.append(
                AttributeDefinitionIssue(f"{at}.fieldType", "ATTRIBUTE_FIELD_TYPE_NOT_ALLOWED")
            )
        else:
            config = attribute.get("config")
            issues.extend(_lint_config(at, field.key, {} if config is None else config))
    return issues


def compile_schema(attributes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The Draft 2020-12 object schema for a lint-clean attribute list (unknown keys rejected)."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for attribute in attributes:
        field = get_field_type(attribute["fieldType"])
        assert field is not None  # only called on a lint-clean list
        properties[attribute["key"]] = field.value_schema(attribute.get("config") or {})
        if attribute.get("required", False):
            required.append(attribute["key"])
    return {
        "$schema": _DRAFT,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }
