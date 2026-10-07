"""PII and credential scrubber for log output (OPS-04).

``scrub(value)`` returns a copy of ``value`` with

- email addresses replaced by ``[email]``;
- ``Bearer <token>`` replaced by ``Bearer [redacted]``;
- ``...token=``, ``...password=`` and ``...secret=`` query/form pairs given a ``[redacted]`` value;
- the value of any mapping key named ``password``, ``token``, ``pin``, ``secret`` or
  ``authorization`` (case-insensitive, also ``*_token``, ``*_password`` and ``*_secret``)
  replaced by ``[redacted]``.

Mappings, lists and tuples are walked recursively (tuples come back as lists, as JSON would render
them). ``str``, ``int``, ``float``, ``bool`` and ``None`` keep their type; anything else is turned
into its ``str()`` and scrubbed, so an object's text can't smuggle an email past the renderer.

``scrub_processor`` applies it to a whole structlog event dict; it runs last before rendering.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

__all__ = ["REDACTED", "scrub", "scrub_processor"]

REDACTED = "[redacted]"
EMAIL_MASK = "[email]"

_SENSITIVE_KEYS = frozenset({"password", "token", "pin", "secret", "authorization"})
_SENSITIVE_SUFFIXES = ("_token", "_password", "_secret", "-token", "-password", "-secret")

_EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[^\s,;\"']+")
_QUERY_PAIR = re.compile(r"(?i)\b([A-Za-z0-9_.-]*(?:token|password|passwd|secret))=[^&\s\"'#]*")
_RECURSION_LIMIT = 32


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return lowered in _SENSITIVE_KEYS or lowered.endswith(_SENSITIVE_SUFFIXES)


def _scrub_text(text: str) -> str:
    text = _BEARER.sub(rf"\1 {REDACTED}", text)
    text = _QUERY_PAIR.sub(rf"\1={REDACTED}", text)
    return _EMAIL.sub(EMAIL_MASK, text)


def _scrub(value: object, depth: int) -> object:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _scrub_text(value)
    if depth >= _RECURSION_LIMIT:
        return REDACTED
    if isinstance(value, Mapping):
        items: Mapping[object, object] = value  # pyright: ignore[reportUnknownVariableType]
        return {
            k: REDACTED if _is_sensitive_key(k) else _scrub(v, depth + 1) for k, v in items.items()
        }
    if isinstance(value, list | tuple):
        seq: list[object] | tuple[object, ...] = value  # pyright: ignore[reportUnknownVariableType]
        return [_scrub(v, depth + 1) for v in seq]
    return _scrub_text(str(value))


def scrub(value: object) -> object:
    """Return ``value`` with emails, bearer tokens and secret values redacted (see module doc)."""
    return _scrub(value, 0)


def scrub_processor(
    logger: object, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: scrub every key of the event dict (``event`` included)."""
    for key in list(event_dict):
        event_dict[key] = REDACTED if _is_sensitive_key(key) else scrub(event_dict[key])
    return event_dict
