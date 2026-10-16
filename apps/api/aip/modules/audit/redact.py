"""Secret redaction before an event is hashed into either audit chain (AUDIT-02 step 4).

The value of any key matching ``password|secret|token|otp|recovery|private_key`` (ignoring case),
at any depth, becomes ``"[redacted]"``. It runs before the hash, so no chain ever holds a secret and
redaction cannot be undone by re-hashing. Keys are matched, never values: free text that mentions a
password is kept.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

__all__ = ["REDACTED", "SECRET_KEY", "redact"]

REDACTED: Final = "[redacted]"
SECRET_KEY: Final = re.compile(r"password|secret|token|otp|recovery|private_key", re.IGNORECASE)


def redact(value: Any) -> Any:
    """A copy of ``value`` with every secret-named key's value replaced by ``"[redacted]"``."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED if isinstance(key, str) and SECRET_KEY.search(key) else redact(item)
            for key, item in value.items()  # pyright: ignore[reportUnknownVariableType]
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value
