"""A minimal, allow-listed JSONLogic evaluator for transition guards (APPROVALS-02 Part B).

Python has no maintained port of ``json-logic-js``, so this implements only the operators a guard
may use (ADR 0035), with the semantics of jsonlogic.com:

``== != === !== < <= > >= ! !! and or if var missing missing_some in``

Everything else (``some all none map reduce filter merge method``, string and arithmetic
operators, any custom operator) is refused by ``validate_guard``, which also caps a guard at
depth 20, 200 nodes and 8 KB serialised. ``evaluate_guard`` validates again, deep-freezes ``data``
(mappings become read-only, lists become tuples) and never registers an operation, so a guard can
only read the facts it is given. Any failure raises ``GuardError``.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, Final

__all__ = ["ALLOWED_OPERATORS", "GuardError", "evaluate_guard", "truthy", "validate_guard"]

MAX_DEPTH: Final = 20
MAX_NODES: Final = 200
MAX_BYTES: Final = 8 * 1024

ALLOWED_OPERATORS: frozenset[str] = frozenset(
    {
        "==",
        "!=",
        "===",
        "!==",
        "<",
        "<=",
        ">",
        ">=",
        "!",
        "!!",
        "and",
        "or",
        "if",
        "var",
        "missing",
        "missing_some",
        "in",
    }
)


# The decimal numeric literals JavaScript's Number() accepts (hex/octal/binary forms omitted).
_JS_NUMBER: Final = re.compile(
    r"[+-]?(?:Infinity|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)", re.ASCII
)


class GuardError(ValueError):
    """The guard is not allowed, or evaluating it failed."""


def _operator(node: Mapping[str, Any]) -> str:
    if len(node) != 1:
        raise GuardError("a guard operation has exactly one operator")
    return next(iter(node))


def _walk(node: object, depth: int, count: list[int]) -> None:
    if depth > MAX_DEPTH:
        raise GuardError("guard too deep")
    count[0] += 1
    if count[0] > MAX_NODES:
        raise GuardError("guard too large")
    if isinstance(node, Mapping):
        op = _operator(node)  # pyright: ignore[reportUnknownArgumentType]
        if op not in ALLOWED_OPERATORS:
            raise GuardError(f"operator not allowed: {op}")
        _walk(node[op], depth + 1, count)
    elif isinstance(node, list | tuple):
        for item in node:  # pyright: ignore[reportUnknownVariableType]
            _walk(item, depth + 1, count)
    elif not (node is None or isinstance(node, str | int | float | bool)):
        raise GuardError(f"not a JSON value: {type(node).__name__}")


def validate_guard(expr: object) -> None:
    """Raise ``GuardError`` unless ``expr`` is an allowed guard within the size limits."""
    if not isinstance(expr, Mapping):
        raise GuardError("a guard is a JSONLogic operation (an object)")
    try:
        size = len(json.dumps(expr, separators=(",", ":")).encode())
    except (TypeError, ValueError) as exc:
        raise GuardError("guard is not JSON") from exc
    if size > MAX_BYTES:
        raise GuardError("guard too large")
    _walk(expr, 1, [0])


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list | tuple):
        return tuple(_freeze(v) for v in value)  # pyright: ignore[reportUnknownVariableType]
    return value


def truthy(value: object) -> bool:
    """JSONLogic truthiness: like JavaScript (every object is true), except an empty array is
    false."""
    if isinstance(value, Mapping):
        return True
    if isinstance(value, list | tuple):
        return len(value) > 0  # pyright: ignore[reportUnknownArgumentType]
    if isinstance(value, float) and math.isnan(value):
        return False
    return bool(value) if value is not None else False


def _number(value: object) -> float:
    """JavaScript ``Number(value)`` for JSON values (NaN when it has none)."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0.0
        if not _JS_NUMBER.fullmatch(text):  # float() would also take "inf", "1_0", other digits
            return math.nan
        return float(text)
    return math.nan


def _strict_equal(a: object, b: object) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return a == b
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return a is b  # arrays and objects compare by identity, as in JavaScript


def _loose_equal(a: object, b: object) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, list | tuple | Mapping) or isinstance(b, list | tuple | Mapping):
        return a is b
    if type(a) is type(b) or (isinstance(a, str) and isinstance(b, str)):
        return _strict_equal(a, b)
    return _number(a) == _number(b)  # number, string and boolean meet as numbers


def _compare(a: object, b: object, op: Callable[[Any, Any], bool]) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return op(a, b)
    x, y = _number(a), _number(b)
    if math.isnan(x) or math.isnan(y):
        return False
    return op(x, y)


def _less(args: Sequence[object], strict: bool) -> bool:
    def op(x: Any, y: Any) -> bool:
        return bool(x < y) if strict else bool(x <= y)

    if len(args) == 3:  # "between": a < b < c
        return _compare(args[0], args[1], op) and _compare(args[1], args[2], op)
    return _compare(args[0], args[1], op)


def _lookup(data: object, path: object, default: object = None) -> object:
    if path is None or path == "" or (isinstance(path, list | tuple) and not path):
        return data
    current = data
    for part in str(path).split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return default
            current = current[part]  # pyright: ignore[reportUnknownVariableType]
        elif isinstance(current, list | tuple) and part.isdigit():
            index = int(part)
            if index >= len(current):  # pyright: ignore[reportUnknownArgumentType]
                return default
            current = current[index]  # pyright: ignore[reportUnknownVariableType]
        else:
            return default
    return current  # pyright: ignore[reportUnknownVariableType]


def _missing(data: object, keys: Sequence[object]) -> list[object]:
    return [k for k in keys if _lookup(data, k) in (None, "")]


def _args(raw: object) -> list[object]:
    if isinstance(raw, list | tuple):
        return list(raw)  # pyright: ignore[reportUnknownArgumentType]
    return [raw]


def _apply(node: object, data: object) -> object:
    if isinstance(node, list | tuple):
        return [_apply(item, data) for item in node]  # pyright: ignore[reportUnknownVariableType]
    if not isinstance(node, Mapping):
        return node
    op = _operator(node)  # pyright: ignore[reportUnknownArgumentType]
    if op not in ALLOWED_OPERATORS:
        raise GuardError(f"operator not allowed: {op}")
    raw = _args(node[op])

    # Lazy operators evaluate only the branches they need.
    if op == "if":
        i = 0
        while i + 1 < len(raw):
            if truthy(_apply(raw[i], data)):
                return _apply(raw[i + 1], data)
            i += 2
        return _apply(raw[i], data) if i < len(raw) else None
    if op in ("and", "or"):
        if not raw:
            raise GuardError(f"{op} needs at least one argument")
        value: object = None
        for item in raw:
            value = _apply(item, data)
            if truthy(value) is (op == "or"):
                return value
        return value

    args = [_apply(item, data) for item in raw]
    operation = _OPERATIONS.get(op)
    if operation is None:
        raise GuardError(f"operator not allowed: {op}")
    return operation(data, args)


def _need(args: Sequence[object], n: int, op: str) -> None:
    if len(args) < n:
        raise GuardError(f"{op} needs {n} arguments")


def _eq(fn: Callable[[object, object], bool], negate: bool, op: str) -> _Operation:
    def operation(data: object, args: list[object]) -> object:
        _need(args, 2, op)
        return fn(args[0], args[1]) is not negate

    return operation


def _var(data: object, args: list[object]) -> object:
    return _lookup(data, args[0] if args else None, args[1] if len(args) > 1 else None)


def _missing_op(data: object, args: list[object]) -> object:
    keys = args[0] if len(args) == 1 and isinstance(args[0], list) else args
    return _missing(data, keys)  # pyright: ignore[reportUnknownArgumentType]


def _missing_some(data: object, args: list[object]) -> object:
    _need(args, 2, "missing_some")
    minimum, keys = args[0], args[1]
    if not isinstance(minimum, int) or not isinstance(keys, list):
        raise GuardError("missing_some needs [minimum, [keys]]")
    absent = _missing(data, keys)  # pyright: ignore[reportUnknownArgumentType]
    return [] if len(keys) - len(absent) >= minimum else absent  # pyright: ignore[reportUnknownArgumentType]


def _in(data: object, args: list[object]) -> object:
    _need(args, 2, "in")
    needle, haystack = args[0], args[1]
    if isinstance(haystack, str):
        return isinstance(needle, str) and needle in haystack
    if isinstance(haystack, list | tuple):
        return any(_strict_equal(needle, item) for item in haystack)  # pyright: ignore[reportUnknownVariableType]
    return False


def _compare_op(op: str, fn: Callable[[Any, Any], bool]) -> _Operation:
    def operation(data: object, args: list[object]) -> object:
        _need(args, 2, op)
        return _compare(args[0], args[1], fn)

    return operation


def _less_op(op: str, *, strict: bool) -> _Operation:
    def operation(data: object, args: list[object]) -> object:
        _need(args, 2, op)
        return _less(args, strict)

    return operation


_Operation = Callable[[object, list[object]], object]

_OPERATIONS: dict[str, _Operation] = {
    "==": _eq(_loose_equal, False, "=="),
    "!=": _eq(_loose_equal, True, "!="),
    "===": _eq(_strict_equal, False, "==="),
    "!==": _eq(_strict_equal, True, "!=="),
    "<": _less_op("<", strict=True),
    "<=": _less_op("<=", strict=False),
    ">": _compare_op(">", lambda x, y: x > y),
    ">=": _compare_op(">=", lambda x, y: x >= y),
    "!": lambda data, args: not truthy(args[0] if args else None),
    "!!": lambda data, args: truthy(args[0] if args else None),
    "var": _var,
    "missing": _missing_op,
    "missing_some": _missing_some,
    "in": _in,
}


def evaluate_guard(expr: object, data: Mapping[str, Any]) -> object:
    """The guard's value for ``data`` (read-only). Raises ``GuardError`` on any failure."""
    validate_guard(expr)
    frozen = _freeze(data)
    try:
        return _apply(expr, frozen)
    except GuardError:
        raise
    except (TypeError, ValueError, KeyError, IndexError, RecursionError) as exc:
        raise GuardError(f"guard evaluation failed: {type(exc).__name__}") from exc
