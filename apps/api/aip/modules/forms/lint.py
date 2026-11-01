"""Lint a form-template revision ``schema`` (FORMS-01).

``lint_template`` is pure: it takes the field-type keys and a unit predicate, so it runs without a
database (the service wires in ``item_types`` and ``terms``). It returns every problem as a
:class:`LintIssue` ``{path, code, message, severity}``, sorted by path, with stable codes the terms
dictionary renders (``forms.lint.<CODE>``). Every issue is an ``error`` (it blocks upload and
publish) except ``RULE_READS_HIDDEN_FIELD``, a ``warning`` the ``/lint`` route reports but publish
allows.

Check order (``SCHEMA_INVALID`` gates the rest; everything after it is collected together):

1. ``SCHEMA_INVALID`` — the JSON Schema contract (``contract.py``). When any fire, only these are
   returned, because the later checks assume a well-shaped document.
2. ``TEMPLATE_TOO_LARGE`` — over 256 KB serialised or over 500 fields.
3. ``DUPLICATE_KEY`` — a key reused (section, field and section-rule keys share one namespace).
4. ``UNKNOWN_FIELD_TYPE`` — a ``type`` not in the field-type registry (its config checks then skip).
5. ``OPTIONS_REQUIRED`` / ``OPTIONS_NOT_ALLOWED`` / ``DUPLICATE_OPTION``.
6. ``UNIT_REQUIRED`` / ``UNKNOWN_UNIT`` — a ``measurement``'s unit.
7. ``VALIDATION_NOT_ALLOWED`` / ``VALIDATION_RANGE``.
8. ``EXPRESSION_INVALID`` — a guard the approvals allow-list refuses (message is the guard error).
9. ``UNKNOWN_REFERENCE`` — a ``var`` reading a non-field answer or an unknown context key.
10. ``CONDITION_CYCLE`` — a cycle among ``visibleIf``/``requiredIf`` references (self included).
11. ``RULE_READS_HIDDEN_FIELD`` (warning, FORMS-10) — a section rule reads a field of another
    section that has a ``visibleIf``, so the field can be hidden (and read as ``null``) while the
    rule's own section is visible.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from aip.modules.approvals.api import GuardError, validate_guard
from aip.modules.forms.contract import validator

__all__ = ["LintIssue", "is_error", "lint_template"]

MAX_BYTES = 256 * 1024
MAX_FIELDS = 500

# The validation keys each field type may carry; a key outside its set is VALIDATION_NOT_ALLOWED.
_BOUNDS = frozenset({"min", "max"})
_LENGTHS = frozenset({"minLength", "maxLength"})
_COUNTS = frozenset({"minItems", "maxItems"})
_VALIDATION_KEYS: dict[str, frozenset[str]] = {
    "number": _BOUNDS,
    "decimal": _BOUNDS,
    "measurement": _BOUNDS,
    "text": _LENGTHS,
    "multi_select": _COUNTS,
    "photo": _COUNTS,
}
_OPTION_TYPES = frozenset({"dropdown", "multi_select"})
_RANGE_PAIRS = (("min", "max"), ("minLength", "maxLength"), ("minItems", "maxItems"))
_CONTEXT_KEYS = frozenset({"kind", "assetId", "projectId"})

Path = list[str | int]


@dataclass(frozen=True, slots=True)
class LintIssue:
    """One problem with a template: ``path`` into the schema, a stable ``code``, a message and a
    ``severity`` (``error`` blocks upload and publish, ``warning`` does not)."""

    path: Path = field(default_factory=list)
    code: str = ""
    message: str = ""
    severity: str = "error"

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": list(self.path),
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


def is_error(issue: LintIssue) -> bool:
    """Whether ``issue`` blocks upload and publish (every severity but ``warning``)."""
    return issue.severity != "warning"


def _sort_key(issue: LintIssue) -> tuple[Any, ...]:
    # Mixed str/int path elements never compare directly; rank ints before strs, then by value.
    return (tuple((0, p) if isinstance(p, int) else (1, p) for p in issue.path), issue.code)


def lint_template(
    schema: Mapping[str, Any],
    *,
    field_types: Collection[str],
    known_units: Callable[[str], bool],
) -> list[LintIssue]:
    """Every problem with ``schema``, sorted by path; ``[]`` when it is a valid template."""
    schema_issues = _schema_issues(schema)
    if schema_issues:
        return sorted(schema_issues, key=_sort_key)

    issues: list[LintIssue] = []
    issues += _size_issues(schema)
    issues += _duplicate_key_issues(schema)

    field_keys = {f["key"] for section in schema["sections"] for f in section["fields"]}
    for s, section in enumerate(schema["sections"]):
        _expression_issues(
            section.get("visibleIf"), ["sections", s, "visibleIf"], field_keys, issues
        )
        for fi, fld in enumerate(section["fields"]):
            base: Path = ["sections", s, "fields", fi]
            issues += _field_issues(fld, base, field_types, known_units)
            for name in ("visibleIf", "requiredIf", "failWhen"):
                _expression_issues(fld.get(name), [*base, name], field_keys, issues)
            for ri, rule in enumerate(fld.get("rules", [])):
                _expression_issues(
                    rule.get("rule"), [*base, "rules", ri, "rule"], field_keys, issues
                )
        for ri, rule in enumerate(section.get("rules", [])):
            _expression_issues(
                rule.get("expr"), ["sections", s, "rules", ri, "expr"], field_keys, issues
            )

    issues += _cycle_issues(schema, field_keys)
    issues += _hidden_read_issues(schema, field_keys)
    return sorted(issues, key=_sort_key)


# --- 1. schema ---------------------------------------------------------------------------------


def _schema_issues(schema: Mapping[str, Any]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for error in validator().iter_errors(schema):  # pyright: ignore[reportUnknownMemberType]
        path: Path = [p for p in error.absolute_path]  # pyright: ignore[reportUnknownVariableType]
        if error.validator == "additionalProperties" and isinstance(error.instance, dict):
            allowed = error.schema.get("properties", {}) if isinstance(error.schema, dict) else {}
            extra = sorted(k for k in error.instance if k not in allowed)  # pyright: ignore[reportUnknownVariableType]
            for key in extra:
                issues.append(LintIssue([*path, key], "SCHEMA_INVALID", error.message))
            if extra:
                continue
        issues.append(LintIssue(path, "SCHEMA_INVALID", error.message))
    return issues


# --- 2. size -----------------------------------------------------------------------------------


def _size_issues(schema: Mapping[str, Any]) -> list[LintIssue]:
    serialised = len(json.dumps(schema, separators=(",", ":"), ensure_ascii=False).encode())
    fields = sum(len(section["fields"]) for section in schema["sections"])
    if serialised > MAX_BYTES or fields > MAX_FIELDS:
        return [LintIssue([], "TEMPLATE_TOO_LARGE", "template exceeds 256 KB or 500 fields")]
    return []


# --- 3. duplicate keys -------------------------------------------------------------------------


def _duplicate_key_issues(schema: Mapping[str, Any]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    seen: set[str] = set()
    for s, section in enumerate(schema["sections"]):
        key = section["key"]
        if key in seen:
            issues.append(
                LintIssue(["sections", s, "key"], "DUPLICATE_KEY", f"duplicate key {key!r}")
            )
        seen.add(key)
        for fi, fld in enumerate(section["fields"]):
            fkey = fld["key"]
            if fkey in seen:
                issues.append(
                    LintIssue(
                        ["sections", s, "fields", fi, "key"],
                        "DUPLICATE_KEY",
                        f"duplicate key {fkey!r}",
                    )
                )
            seen.add(fkey)
        for ri, rule in enumerate(section.get("rules", [])):
            rkey = rule["key"]
            if rkey in seen:
                issues.append(
                    LintIssue(
                        ["sections", s, "rules", ri, "key"],
                        "DUPLICATE_KEY",
                        f"duplicate key {rkey!r}",
                    )
                )
            seen.add(rkey)
    return issues


# --- 4-7. per-field type, options, unit, validations -------------------------------------------


def _field_issues(
    fld: Mapping[str, Any],
    base: Path,
    field_types: Collection[str],
    known_units: Callable[[str], bool],
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    ftype = fld["type"]
    if ftype not in field_types:
        return [LintIssue([*base, "type"], "UNKNOWN_FIELD_TYPE", f"unknown field type {ftype!r}")]

    options = fld.get("options")
    if ftype in _OPTION_TYPES:
        if options is None:
            issues.append(
                LintIssue([*base, "options"], "OPTIONS_REQUIRED", f"{ftype} needs options")
            )
        else:
            values_seen: set[str] = set()
            for oi, option in enumerate(options):
                value = option["value"]
                if value in values_seen:
                    issues.append(
                        LintIssue(
                            [*base, "options", oi, "value"],
                            "DUPLICATE_OPTION",
                            f"duplicate option {value!r}",
                        )
                    )
                values_seen.add(value)
    elif options is not None:
        issues.append(
            LintIssue([*base, "options"], "OPTIONS_NOT_ALLOWED", f"{ftype} does not take options")
        )

    if ftype == "measurement":
        unit = fld.get("unit")
        if unit is None:
            issues.append(LintIssue([*base, "unit"], "UNIT_REQUIRED", "measurement needs a unit"))
        elif not known_units(unit):
            issues.append(LintIssue([*base, "unit"], "UNKNOWN_UNIT", f"unknown unit {unit!r}"))

    issues += _validation_issues(fld, ftype, base)
    return issues


def _validation_issues(fld: Mapping[str, Any], ftype: str, base: Path) -> list[LintIssue]:
    validations = fld.get("validations")
    if not validations:
        return []
    issues: list[LintIssue] = []
    allowed = _VALIDATION_KEYS.get(ftype, frozenset())
    for name in sorted(validations):
        if name not in allowed:
            issues.append(
                LintIssue(
                    [*base, "validations", name],
                    "VALIDATION_NOT_ALLOWED",
                    f"{ftype} does not allow {name}",
                )
            )
    for low, high in _RANGE_PAIRS:
        if (
            low in allowed
            and low in validations
            and high in validations
            and validations[low] > validations[high]
        ):
            issues.append(
                LintIssue(
                    [*base, "validations", low],
                    "VALIDATION_RANGE",
                    f"{low} is greater than {high}",
                )
            )
    return issues


# --- 8-9. expressions --------------------------------------------------------------------------


def _expression_issues(
    expr: object, path: Path, field_keys: set[str], issues: list[LintIssue]
) -> None:
    if expr is None:
        return
    try:
        validate_guard(expr)
    except GuardError as exc:
        issues.append(LintIssue(path, "EXPRESSION_INVALID", str(exc)))
        return
    for var in _iter_vars(expr):
        if not isinstance(var, str):
            continue
        if var.startswith("answers.") and var.split(".")[1] not in field_keys:
            issues.append(LintIssue(path, "UNKNOWN_REFERENCE", f"unknown answer reference {var!r}"))
        elif var.startswith("context.") and var.split(".")[1] not in _CONTEXT_KEYS:
            issues.append(
                LintIssue(path, "UNKNOWN_REFERENCE", f"unknown context reference {var!r}")
            )


def _iter_vars(node: object) -> Iterator[object]:
    """Yield the first argument of every ``{"var": ...}`` operation in ``node``."""
    if isinstance(node, Mapping):
        if set(node) == {"var"}:
            arg = node["var"]
            yield arg[0] if isinstance(arg, list) and arg else arg
            return
        for value in node.values():
            yield from _iter_vars(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_vars(item)


# --- 10. condition cycles ----------------------------------------------------------------------


def _cycle_issues(schema: Mapping[str, Any], field_keys: set[str]) -> list[LintIssue]:
    """One issue when ``visibleIf``/``requiredIf`` references form a cycle (self-reference counts).

    ``failWhen`` and ``rules`` are left out: a field's own value legitimately drives those.
    """
    graph: dict[str, set[str]] = {}
    for section in schema["sections"]:
        targets = _reads(section.get("visibleIf"), field_keys)
        graph.setdefault(section["key"], set()).update(targets)
        for fld in section["fields"]:
            reads: set[str] = set()
            reads |= _reads(fld.get("visibleIf"), field_keys)
            reads |= _reads(fld.get("requiredIf"), field_keys)
            graph.setdefault(fld["key"], set()).update(reads)

    if _has_cycle(graph):
        return [LintIssue([], "CONDITION_CYCLE", "visibleIf/requiredIf references form a cycle")]
    return []


def _reads(expr: object, field_keys: set[str]) -> set[str]:
    """Field keys an expression reads via ``answers.<key>`` (an invalid guard reads nothing)."""
    if expr is None:
        return set()
    try:
        validate_guard(expr)
    except GuardError:
        return set()
    out: set[str] = set()
    for var in _iter_vars(expr):
        if isinstance(var, str) and var.startswith("answers."):
            key = var.split(".")[1]
            if key in field_keys:
                out.add(key)
    return out


def _has_cycle(graph: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()  # on the current DFS stack (a grey node)
    done: set[str] = set()  # fully explored (a black node)

    def visit(node: str) -> bool:
        visiting.add(node)
        for nxt in graph.get(node, ()):
            if nxt not in graph:
                continue
            if nxt in visiting or (nxt not in done and visit(nxt)):
                return True
        visiting.discard(node)
        done.add(node)
        return False

    return any(node not in done and visit(node) for node in graph)


# --- 11. section rules reading a field that can be hidden --------------------------------------


def _hidden_read_issues(schema: Mapping[str, Any], field_keys: set[str]) -> list[LintIssue]:
    """A warning per section rule that reads a field of another, conditionally visible, section.

    That field can be hidden while the rule's own section is visible; the rule then reads it as
    ``null``. Authors may mean it (a rule that tolerates the absence), so it does not block publish.
    """
    hideable: dict[str, str] = {}  # field key -> its section key, for sections with a visibleIf
    for section in schema["sections"]:
        if section.get("visibleIf") is not None:
            for fld in section["fields"]:
                hideable[fld["key"]] = section["key"]

    issues: list[LintIssue] = []
    for s, section in enumerate(schema["sections"]):
        for ri, rule in enumerate(section.get("rules", [])):
            for key in sorted(_reads(rule.get("expr"), field_keys)):
                other = hideable.get(key)
                if other is not None and other != section["key"]:
                    issues.append(
                        LintIssue(
                            ["sections", s, "rules", ri, "expr"],
                            "RULE_READS_HIDDEN_FIELD",
                            f"rule reads {key!r} in section {other!r}, which can be hidden",
                            "warning",
                        )
                    )
    return issues
