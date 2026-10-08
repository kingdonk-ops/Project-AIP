"""Validate JSONB ``attributes`` against the per-type JSON Schema stored in the database.

Request bodies are validated by Pydantic; the schemas that admins define per asset or document
type live in rows, so they are validated here with ``jsonschema`` (Draft 2020-12). Errors carry a
JSON path and a terminology key (``validation.attribute.<keyword>``), never an English label: the
client renders the key through the terms dictionary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from aip.platform.db.errors import InvalidSchemaError

__all__ = ["AttributeValidationError", "validate_attributes"]


@dataclass(frozen=True)
class AttributeValidationError:
    """One failed constraint. ``path`` is like ``$.wall_loss_mm`` or ``$.readings[2]``."""

    path: str
    term_key: str
    params: dict[str, Any] = field(default_factory=lambda: {})


def _json_path(parts: Any) -> str:
    out = "$"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _convert(error: ValidationError) -> AttributeValidationError:
    keyword = str(error.validator)
    path_parts = list(error.absolute_path)
    params: dict[str, Any] = {}
    if keyword == "required":
        # ``required`` is reported on the object, once per missing property: point at that one.
        instance: dict[str, Any] = error.instance  # pyright: ignore[reportAssignmentType]
        names: list[str] = list(error.validator_value)  # pyright: ignore[reportArgumentType, reportUnknownVariableType]
        for name in names:
            if name not in instance and error.message == f"{name!r} is a required property":
                path_parts.append(name)
                break
    elif keyword in {"type", "enum", "const", "format"}:
        params[keyword] = error.validator_value
    elif keyword in {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "multipleOf",
        "pattern",
    }:
        params["limit"] = error.validator_value
    return AttributeValidationError(
        _json_path(path_parts), f"validation.attribute.{keyword}", params
    )


def validate_attributes(
    type_schema: dict[str, Any], value: dict[str, Any]
) -> list[AttributeValidationError]:
    """All violations of ``type_schema`` by ``value``, ordered by path; empty when valid.

    Raises ``InvalidSchemaError`` when ``type_schema`` is not a valid Draft 2020-12 schema.
    """
    try:
        Draft202012Validator.check_schema(type_schema)
    except SchemaError as exc:
        raise InvalidSchemaError(exc.message) from exc
    validator = Draft202012Validator(
        type_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    errors = [_convert(e) for e in validator.iter_errors(value)]  # pyright: ignore[reportUnknownMemberType]
    return sorted(errors, key=lambda e: (e.path, e.term_key))
