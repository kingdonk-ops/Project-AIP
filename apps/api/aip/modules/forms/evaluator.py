"""The shared form answer evaluator (FORMS-02).

Given a frozen revision ``schema`` and a set of ``answers`` it decides which fields are visible and
required, which answers are invalid and which answers fail. It is pure — no database, no I/O — and
reaches JSONLogic only through the approvals published interface
(``aip.modules.approvals.api.evaluate_guard``/``truthy`` and ``GuardError``), never a copy of the
evaluator. The TypeScript twin in ``packages/form-renderer`` follows the same semantics on the same
golden vectors (``packages/contracts/jsonlogic-vectors/forms``); see that folder's README for the
authoritative spec.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from aip.modules.approvals.api import GuardError, evaluate_guard, truthy

__all__ = [
    "EVALUATOR_VERSION",
    "AnswerError",
    "AnswerEvaluation",
    "ExpressionError",
    "evaluate_answers",
    "evaluation_as_json",
]

EVALUATOR_VERSION: Final = "1"

_MISSING: Final = object()  # a sentinel: an answer key that is absent, distinct from ``None``

_OPTION_TYPES: Final = frozenset({"dropdown", "multi_select"})
_DATE_RE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UUID_RE: Final = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True, slots=True)
class AnswerError:
    """One problem with a single answer; at most one per field (first match wins)."""

    field_key: str
    code: str
    message_key: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExpressionError:
    """A guard that raised while evaluating; the field fails closed and is reported here."""

    field_key: str
    expression: str  # "visibleIf" | "requiredIf" | "failWhen" | "rule"
    message: str


@dataclass(frozen=True, slots=True)
class AnswerEvaluation:
    """The verdict for one set of answers against one revision schema."""

    visible: dict[str, bool]
    required: dict[str, bool]
    errors: list[AnswerError]
    failed: list[str]
    ignored: list[str]
    expression_errors: list[ExpressionError]
    complete: bool


def evaluation_as_json(evaluation: AnswerEvaluation) -> dict[str, Any]:
    """The evaluation as the camelCase JSON both implementations compare and the route returns."""
    return {
        "visible": evaluation.visible,
        "required": evaluation.required,
        "errors": [
            {
                "fieldKey": e.field_key,
                "code": e.code,
                "messageKey": e.message_key,
                "params": e.params,
            }
            for e in evaluation.errors
        ],
        "failed": evaluation.failed,
        "ignored": evaluation.ignored,
        "expressionErrors": [
            {"fieldKey": e.field_key, "expression": e.expression, "message": e.message}
            for e in evaluation.expression_errors
        ],
        "complete": evaluation.complete,
    }


# --- small answer helpers ----------------------------------------------------------------------


def _is_empty(value: object, ftype: str) -> bool:
    if value is _MISSING or value is None or value == "" or value == []:
        return True
    if ftype == "measurement" and isinstance(value, Mapping):
        return value.get("value") is None  # pyright: ignore[reportUnknownMemberType]
    return False


def _is_integer_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value) and value.is_integer()
    return False


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int | float) and math.isfinite(value)


def _is_real_date(value: object) -> bool:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return False
    year, month, day = int(value[0:4]), int(value[5:7]), int(value[8:10])
    if month < 1 or month > 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return 1 <= day <= days[month - 1]


def _is_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def _is_file_ref(value: object) -> bool:
    return isinstance(value, Mapping) and set(value) == {"fileId"} and _is_uuid(value["fileId"])


def _type_ok(ftype: str, value: object, unit: object) -> bool:
    if ftype == "text":
        return isinstance(value, str)
    if ftype == "number":
        return _is_integer_number(value)
    if ftype == "decimal":
        return _is_finite_number(value)
    if ftype == "date":
        return _is_real_date(value)
    if ftype == "dropdown":
        return isinstance(value, str)
    if ftype == "multi_select":
        return (
            isinstance(value, list)
            and all(isinstance(v, str) for v in value)
            and len(set(value)) == len(value)
        )
    if ftype == "measurement":
        return (
            isinstance(value, Mapping)
            and _is_finite_number(value.get("value"))
            and value.get("unit") == unit
        )
    if ftype == "boolean":
        return isinstance(value, bool)
    if ftype == "photo":
        return isinstance(value, list) and all(_is_file_ref(v) for v in value)
    if ftype == "signature":
        return _is_file_ref(value)
    if ftype in ("asset_ref", "user_ref"):
        return _is_uuid(value)
    return False


# --- field model and ordering ------------------------------------------------------------------


@dataclass(slots=True)
class _Field:
    key: str
    section_key: str
    type: str
    spec: Mapping[str, Any]
    doc_index: int


def _order(schema: Mapping[str, Any]) -> tuple[list[str], dict[str, _Field], dict[str, Any]]:
    """Return (topological node order, field index, section index), ties by document order."""
    fields: dict[str, _Field] = {}
    sections: dict[str, Any] = {}
    doc: dict[str, int] = {}
    nxt = 0
    for section in schema["sections"]:
        skey = section["key"]
        sections[skey] = section
        doc[skey] = nxt
        nxt += 1
        for spec in section["fields"]:
            fkey = spec["key"]
            doc[fkey] = nxt
            nxt += 1
            fields[fkey] = _Field(fkey, skey, spec["type"], spec, doc[fkey])

    field_keys = set(fields)
    deps: dict[str, set[str]] = {}
    for skey, section in sections.items():
        deps[skey] = _reads(section.get("visibleIf"), field_keys)
    for fkey, fld in fields.items():
        reads = _reads(fld.spec.get("visibleIf"), field_keys)
        reads |= _reads(fld.spec.get("requiredIf"), field_keys)
        reads.add(fld.section_key)  # a field is placed after its own section
        deps[fkey] = reads

    return _toposort(deps, doc), fields, sections


def _toposort(deps: dict[str, set[str]], doc: dict[str, int]) -> list[str]:
    done: set[str] = set()
    order: list[str] = []
    remaining = set(deps)
    while remaining:
        ready = sorted((n for n in remaining if deps[n] <= done), key=lambda n: doc[n])
        if not ready:  # a residual cycle: break it by document order, deterministically
            ready = [min(remaining, key=lambda n: doc[n])]
        for node in ready:
            order.append(node)
            done.add(node)
            remaining.discard(node)
    return order


def _reads(expr: object, field_keys: set[str]) -> set[str]:
    """Field keys an expression reads via ``answers.<key>``."""
    out: set[str] = set()
    for var in _iter_vars(expr):
        if isinstance(var, str) and var.startswith("answers."):
            key = var[len("answers.") :].split(".")[0]
            if key in field_keys:
                out.add(key)
    return out


def _iter_vars(node: object) -> list[object]:
    out: list[object] = []

    def walk(n: object) -> None:
        if isinstance(n, Mapping):
            if set(n) == {"var"}:
                arg = n["var"]
                out.append(arg[0] if isinstance(arg, list) and arg else arg)
                return
            for value in n.values():
                walk(value)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(node)
    return out


def _guard(expr: object, data: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Evaluate ``expr`` for truthiness; on a ``GuardError`` return ``(True, message)``."""
    try:
        return truthy(evaluate_guard(expr, data)), None
    except GuardError as exc:
        return True, str(exc)


# --- the evaluation ----------------------------------------------------------------------------


def evaluate_answers(
    revision_schema: Mapping[str, Any],
    answers: Mapping[str, Any],
    *,
    mode: str = "submit",
    context: Mapping[str, Any] | None = None,
) -> AnswerEvaluation:
    """Evaluate ``answers`` against ``revision_schema``; the vectors README is the spec."""
    ctx: dict[str, Any] = dict(context) if context else {}
    order, fields, sections = _order(revision_schema)

    visible: dict[str, bool] = {}
    required: dict[str, bool] = {}
    section_visible: dict[str, bool] = {}
    expression_errors: list[ExpressionError] = []
    visible_answers: dict[str, Any] = {}

    def data() -> dict[str, Any]:
        return {"answers": dict(visible_answers), "context": ctx}

    # Pass 1: visibility and required, topologically, accumulating visible answers.
    for node in order:
        if node in sections:
            expr = sections[node].get("visibleIf")
            if expr is None:
                section_visible[node] = True
            else:
                ok, message = _guard(expr, data())
                section_visible[node] = ok
                if message is not None:
                    expression_errors.append(ExpressionError(node, "visibleIf", message))
            continue

        fld = fields[node]
        field_vis = True
        vis_expr = fld.spec.get("visibleIf")
        if vis_expr is not None:
            field_vis, message = _guard(vis_expr, data())
            if message is not None:
                expression_errors.append(ExpressionError(fld.key, "visibleIf", message))
        is_visible = section_visible.get(fld.section_key, True) and field_vis
        visible[fld.key] = is_visible

        if is_visible and fld.key in answers:
            visible_answers[fld.key] = answers[fld.key]

        req = False
        if is_visible:
            if fld.spec.get("required") is True:
                req = True
            else:
                req_expr = fld.spec.get("requiredIf")
                if req_expr is not None:
                    req, message = _guard(req_expr, data())
                    if message is not None:
                        expression_errors.append(ExpressionError(fld.key, "requiredIf", message))
        required[fld.key] = req

    # Pass 2: errors, failed and ignored, in document order.
    errors: list[AnswerError] = []
    failed: list[str] = []
    ignored: list[str] = []
    field_keys = set(fields)
    for fld in sorted(fields.values(), key=lambda f: f.doc_index):
        answer: object = answers.get(fld.key, _MISSING)
        if not visible[fld.key]:
            if answer is not _MISSING:
                ignored.append(fld.key)
            continue

        error = _field_error(fld, answer, required[fld.key], mode, data(), expression_errors)
        if error is not None:
            errors.append(error)

        if not _is_empty(answer, fld.type):
            fail_expr = fld.spec.get("failWhen")
            if fail_expr is not None:
                failing, message = _guard(fail_expr, data())
                if failing:
                    failed.append(fld.key)
                if message is not None:
                    expression_errors.append(ExpressionError(fld.key, "failWhen", message))

    for key in sorted(k for k in answers if k not in field_keys):
        errors.append(AnswerError(key, "UNKNOWN_FIELD", "forms.answer.UNKNOWN_FIELD"))

    return AnswerEvaluation(
        visible=visible,
        required=required,
        errors=errors,
        failed=failed,
        ignored=ignored,
        expression_errors=expression_errors,
        complete=len(errors) == 0,
    )


def _field_error(
    fld: _Field,
    answer: object,
    is_required: bool,
    mode: str,
    data: Mapping[str, Any],
    expression_errors: list[ExpressionError],
) -> AnswerError | None:
    key, ftype = fld.key, fld.type
    if _is_empty(answer, ftype):
        if mode == "submit" and is_required:
            return AnswerError(key, "REQUIRED", "forms.answer.REQUIRED")
        return None

    if not _type_ok(ftype, answer, fld.spec.get("unit")):
        return AnswerError(key, "WRONG_TYPE", "forms.answer.WRONG_TYPE")

    option_error = _option_error(fld, answer)
    if option_error is not None:
        return option_error

    bound_error = _bound_error(fld, answer)
    if bound_error is not None:
        return bound_error

    return _rule_error(fld, data, expression_errors)


def _option_error(fld: _Field, answer: object) -> AnswerError | None:
    if fld.type not in _OPTION_TYPES:
        return None
    values = {opt["value"] for opt in fld.spec.get("options", [])}
    chosen = answer if isinstance(answer, list) else [answer]
    if any(value not in values for value in chosen):
        return AnswerError(fld.key, "NOT_AN_OPTION", "forms.answer.NOT_AN_OPTION")
    return None


def _bound_error(fld: _Field, answer: Any) -> AnswerError | None:
    validations = fld.spec.get("validations") or {}
    if fld.type in ("number", "decimal", "measurement"):
        value = answer["value"] if fld.type == "measurement" else answer
        return _range_error(fld.key, value, validations, "min", "max", "BELOW_MIN", "ABOVE_MAX")
    if fld.type == "text":
        length = len(answer) if isinstance(answer, str) else 0
        return _range_error(
            fld.key, length, validations, "minLength", "maxLength", "TOO_SHORT", "TOO_LONG"
        )
    if fld.type in ("multi_select", "photo"):
        count = len(answer) if isinstance(answer, list) else 0
        return _range_error(
            fld.key, count, validations, "minItems", "maxItems", "TOO_FEW", "TOO_MANY"
        )
    return None


def _range_error(
    key: str,
    value: Any,
    validations: Mapping[str, Any],
    low_key: str,
    high_key: str,
    low_code: str,
    high_code: str,
) -> AnswerError | None:
    low = validations.get(low_key)
    if low is not None and value < low:
        return AnswerError(key, low_code, f"forms.answer.{low_code}", {low_key: low})
    high = validations.get(high_key)
    if high is not None and value > high:
        return AnswerError(key, high_code, f"forms.answer.{high_code}", {high_key: high})
    return None


def _rule_error(
    fld: _Field, data: Mapping[str, Any], expression_errors: list[ExpressionError]
) -> AnswerError | None:
    for rule in fld.spec.get("rules", []):
        passing, message = _guard(rule["rule"], data)
        if message is not None:  # a GuardError: fail closed and report the expression
            expression_errors.append(ExpressionError(fld.key, "rule", message))
            return AnswerError(fld.key, "RULE_FAILED", rule["messageKey"])
        if not passing:
            return AnswerError(fld.key, "RULE_FAILED", rule["messageKey"])
    return None
