"""PII and credential scrubber for log output (OPS-04).

``scrub(value)`` returns a copy of ``value`` with

- email addresses replaced by ``[email]``;
- ``Bearer <token>``, ``Basic <credentials>`` and ``Digest <params>`` auth values redacted;
- ``Cookie:`` / ``Set-Cookie:`` header values redacted to the end of the line;
- ``...token=``, ``...password=``, ``...secret=`` and ``pin=`` query/form pairs given a
  ``[redacted]`` value;
- JSON or repr pairs inside text (``"pin": "1234"``, ``'password': 'x'``, ``"pin": 1234``) for the
  sensitive keys below given a ``[redacted]`` value;
- the value of any mapping key named ``password``, ``token``, ``pin``, ``secret``,
  ``authorization``, ``cookie`` or ``set-cookie`` (case-insensitive, also ``*_token``,
  ``*_password`` and ``*_secret``) replaced by ``[redacted]``.

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

_SENSITIVE_KEYS = frozenset(
    {"password", "token", "pin", "secret", "authorization", "cookie", "set-cookie"}
)
_SENSITIVE_SUFFIXES = ("_token", "_password", "_secret", "-token", "-password", "-secret")

_EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_SECRET_NAME = r"[A-Za-z0-9_.-]*(?:token|password|passwd|secret)"
_TEXT_KEY = rf"(?:{_SECRET_NAME}|pin|authorization|cookie|set-cookie)"

# "key": "value" / 'key': 'value' / "key": 1234 (JSON, Python repr), also with "=" (kwargs repr).
_QUOTED_PAIR = re.compile(
    rf"""(?i)(["'])({_TEXT_KEY})\1(\s*[:=]\s*)"""
    r"""(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^,}\]\s]+)"""
)
_COOKIE_HEADER = re.compile(r"(?im)\b((?:set-)?cookie)(\s*:\s*)[^\r\n]+")
_DIGEST = re.compile(r"(?i)\b(digest)\s+(?=[A-Za-z_]+=)[^\r\n]+")
# Base64 credentials: needs a digit, "+", "/", "=" or a lower-to-upper case change, so prose such as
# "basic validation" is left alone.
_BASIC = re.compile(r"(?i)\b(basic)\s+(?=\S*(?:[0-9+/=]|[a-z](?-i:[A-Z])))[A-Za-z0-9+/]{6,}={0,2}")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[^\s,;\"']+")
_QUERY_PAIR = re.compile(rf"(?i)\b({_SECRET_NAME}|pin)=[^&\s\"'#]*")
_RECURSION_LIMIT = 32


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return lowered in _SENSITIVE_KEYS or lowered.endswith(_SENSITIVE_SUFFIXES)


def _quoted_pair(match: re.Match[str]) -> str:
    quote, key, sep = match.group(1), match.group(2), match.group(3)
    return f"{quote}{key}{quote}{sep}{quote}{REDACTED}{quote}"


def _scrub_text(text: str) -> str:
    text = _QUOTED_PAIR.sub(_quoted_pair, text)
    text = _COOKIE_HEADER.sub(rf"\1\2{REDACTED}", text)
    text = _DIGEST.sub(rf"\1 {REDACTED}", text)
    text = _BASIC.sub(rf"\1 {REDACTED}", text)
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
