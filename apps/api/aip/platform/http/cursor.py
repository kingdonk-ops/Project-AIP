"""Opaque, tamper-evident list cursors (ASSETS-01, from PROJECTS-01's ``cursor.py``).

A cursor is ``base64url(json) + "." + base64url(hmac)``: the JSON holds the sort key and the last
row's sort value and id, and the HMAC-SHA256 (truncated to 16 bytes) stops a client from forging a
position. Cursors are not secret, only unforgeable.

This is the shared platform home for the codec; ``aip.modules.projects.cursor`` keeps its own copy
until a projects follow-up switches it over (ASSETS-01 step 8).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any, cast

__all__ = ["CursorCodec", "InvalidCursorError"]

_MAC_BYTES = 16


class InvalidCursorError(ValueError):
    """The cursor is malformed or was not issued by this server."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise InvalidCursorError("cursor is not base64url") from exc


class CursorCodec:
    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        if len(key) < 16:
            raise ValueError("cursor key must be at least 16 bytes")
        self._key = key

    def _mac(self, body: bytes) -> bytes:
        return hmac.new(self._key, body, hashlib.sha256).digest()[:_MAC_BYTES]

    def encode(self, data: Mapping[str, Any]) -> str:
        body = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
        return f"{_b64encode(body)}.{_b64encode(self._mac(body))}"

    def decode(self, cursor: str) -> dict[str, Any]:
        body_part, sep, mac_part = cursor.partition(".")
        if not sep or not body_part or not mac_part:
            raise InvalidCursorError("cursor is malformed")
        body = _b64decode(body_part)
        if not hmac.compare_digest(_b64decode(mac_part), self._mac(body)):
            raise InvalidCursorError("cursor signature does not match")
        try:
            data = json.loads(body)
        except ValueError as exc:  # a valid MAC over bad JSON only happens with a leaked key
            raise InvalidCursorError("cursor is not JSON") from exc
        if not isinstance(data, dict):
            raise InvalidCursorError("cursor is not an object")
        return cast("dict[str, Any]", data)
