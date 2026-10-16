"""Secret redaction before an event is hashed into either audit chain (AUDIT-02 step 4).

A key is split into words (``api_token`` -> api, token; ``refreshToken`` -> refresh, token;
``PRIVATE_KEY`` -> private, key). Its value becomes ``"[redacted]"`` when a word is one of
password, passwd, secret, token, otp, recovery, credential(s), authorization, cookie or apikey, or
two adjacent words form api key, private key or client secret. Matching whole words keeps keys
such as ``footprint`` (which merely contains "otp"). A ``{"name"|"key": <secret word>, "value": x}``
pair has its ``value`` redacted too. It runs at any depth and before the hash, so no chain ever
holds a secret. Values are never inspected: free text that mentions a password is kept, so
callers must not put secrets in free-text fields (``reason``, ``targetRef``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from itertools import pairwise
from typing import Any, Final

__all__ = ["REDACTED", "is_secret_key", "redact"]

REDACTED: Final = "[redacted]"
SECRET_WORDS: Final = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "otp",
        "recovery",
        "credential",
        "credentials",
        "authorization",
        "cookie",
        "apikey",
    }
)
SECRET_PAIRS: Final = frozenset({("api", "key"), ("private", "key"), ("client", "secret")})
_WORDS: Final = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def is_secret_key(key: str) -> bool:
    words = [w.lower() for w in _WORDS.findall(key)]
    if any(w in SECRET_WORDS for w in words):
        return True
    return any(pair in SECRET_PAIRS for pair in pairwise(words))


def _is_secret_pair(value: Mapping[Any, Any]) -> bool:
    label = value.get("name", value.get("key"))
    return "value" in value and isinstance(label, str) and is_secret_key(label)


def redact(value: Any) -> Any:
    """A copy of ``value`` with every secret-named key's value replaced by ``"[redacted]"``."""
    if isinstance(value, Mapping):
        pair = _is_secret_pair(value)  # pyright: ignore[reportUnknownArgumentType]
        return {
            key: REDACTED
            if (isinstance(key, str) and is_secret_key(key)) or (pair and key == "value")
            else redact(item)
            for key, item in value.items()  # pyright: ignore[reportUnknownVariableType]
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value
