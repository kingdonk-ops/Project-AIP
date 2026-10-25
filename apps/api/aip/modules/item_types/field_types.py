"""The one field-type registry (ITEMTYPES-01, ADR 0036 choice 3).

Item-type attributes and form fields share these field types. Each :class:`FieldType` carries a
``config_schema`` (a Draft 2020-12 JSON Schema of its allowed, mostly optional config keys) and a
``value_schema(config)`` that turns a validated config into the JSON Schema a stored value must
satisfy. There is no English here: a type's label is the term key ``item_types.field_type.<key>``.

``measurement`` units are the SI storage units of the TERMS-03 contract
(``packages/contracts/unit-vectors/units-v1.json``): the entries whose ``si`` equals their own key
(``mm``, ``bar``, ``degC`` today). Values are stored in that unit; display conversion is
``aip.modules.terms.api.to_display`` at presentation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any

__all__ = ["SI_UNITS", "FieldType", "field_types", "get_field_type"]

_DRAFT = "https://json-schema.org/draft/2020-12/schema"

# The SI storage units a ``measurement`` config may name: the TERMS-03 units contract's entries
# whose ``si`` is their own key (``packages/contracts/unit-vectors/units-v1.json``). Hardcoded
# like ``aip.modules.terms.units.UNITS`` rather than read at runtime, because the contract is a
# repo file the installed package does not ship; ``test_field_types`` asserts this matches it.
SI_UNITS: tuple[str, ...] = ("mm", "bar", "degC")


@dataclass(frozen=True, slots=True)
class FieldType:
    """One field type both item-type attributes and form fields can use."""

    key: str
    term_key: str
    usable_in: frozenset[str]
    config_schema: dict[str, Any]
    value_schema: Callable[[dict[str, Any]], dict[str, Any]]


def _config(*, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": _DRAFT,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


_OPTIONS = {
    "type": "array",
    "minItems": 1,
    "maxItems": 200,
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", "label"],
        "properties": {
            "value": {"type": "string", "minLength": 1},
            "label": {"type": "string", "minLength": 1},
        },
    },
}


def _bounds(config: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    schema = dict(base)
    if "min" in config:
        schema["minimum"] = config["min"]
    if "max" in config:
        schema["maximum"] = config["max"]
    return schema


def _text_value(config: dict[str, Any]) -> dict[str, Any]:
    return {"type": "string", "maxLength": config.get("maxLength", 2000)}


def _number_value(config: dict[str, Any]) -> dict[str, Any]:
    return _bounds(config, {"type": "integer"})


def _decimal_value(config: dict[str, Any]) -> dict[str, Any]:
    return _bounds(config, {"type": "number"})


def _date_value(config: dict[str, Any]) -> dict[str, Any]:
    return {"type": "string", "format": "date"}


def _dropdown_value(config: dict[str, Any]) -> dict[str, Any]:
    return {"type": "string", "enum": [option["value"] for option in config["options"]]}


def _multi_select_value(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"enum": [option["value"] for option in config["options"]]},
        "uniqueItems": True,
    }


def _measurement_value(config: dict[str, Any]) -> dict[str, Any]:
    return _bounds(config, {"type": "number"})


def _boolean_value(config: dict[str, Any]) -> dict[str, Any]:
    return {"type": "boolean"}


def _photo_value(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string", "format": "uuid"},
        "maxItems": config.get("maxCount", 1),
    }


def _uuid_value(config: dict[str, Any]) -> dict[str, Any]:
    return {"type": "string", "format": "uuid"}


_ATTRIBUTE_OR_FORM = frozenset({"attribute", "form"})
_FORM_ONLY = frozenset({"form"})


@cache
def _registry() -> tuple[FieldType, ...]:
    def ft(
        key: str,
        usable_in: frozenset[str],
        config_schema: dict[str, Any],
        value_schema: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> FieldType:
        return FieldType(
            key=key,
            term_key=f"item_types.field_type.{key}",
            usable_in=usable_in,
            config_schema=config_schema,
            value_schema=value_schema,
        )

    return (
        ft(
            "text",
            _ATTRIBUTE_OR_FORM,
            _config(properties={"maxLength": {"type": "integer", "minimum": 1, "maximum": 10000}}),
            _text_value,
        ),
        ft(
            "number",
            _ATTRIBUTE_OR_FORM,
            _config(properties={"min": {"type": "integer"}, "max": {"type": "integer"}}),
            _number_value,
        ),
        ft(
            "decimal",
            _ATTRIBUTE_OR_FORM,
            _config(
                properties={
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                    "decimals": {"type": "integer", "minimum": 0, "maximum": 6},
                }
            ),
            _decimal_value,
        ),
        ft("date", _ATTRIBUTE_OR_FORM, _config(properties={}), _date_value),
        ft(
            "dropdown",
            _ATTRIBUTE_OR_FORM,
            _config(properties={"options": _OPTIONS}, required=["options"]),
            _dropdown_value,
        ),
        ft(
            "multi_select",
            _ATTRIBUTE_OR_FORM,
            _config(properties={"options": _OPTIONS}, required=["options"]),
            _multi_select_value,
        ),
        ft(
            "measurement",
            _ATTRIBUTE_OR_FORM,
            _config(
                properties={
                    "unit": {"enum": list(SI_UNITS)},
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                },
                required=["unit"],
            ),
            _measurement_value,
        ),
        ft("boolean", _ATTRIBUTE_OR_FORM, _config(properties={}), _boolean_value),
        ft(
            "photo",
            _FORM_ONLY,
            _config(properties={"maxCount": {"type": "integer", "minimum": 1, "maximum": 20}}),
            _photo_value,
        ),
        ft("signature", _FORM_ONLY, _config(properties={}), _uuid_value),
        ft("asset_ref", _ATTRIBUTE_OR_FORM, _config(properties={}), _uuid_value),
        ft("user_ref", _ATTRIBUTE_OR_FORM, _config(properties={}), _uuid_value),
    )


def field_types() -> tuple[FieldType, ...]:
    """Every field type, in the stable registry order (``text`` first, ``user_ref`` last)."""
    return _registry()


def get_field_type(key: str) -> FieldType | None:
    """The field type with ``key``, or ``None`` when no type has it."""
    return next((f for f in _registry() if f.key == key), None)
