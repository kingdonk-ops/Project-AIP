"""ASSETS-01 unit tests for the shared cursor codec (platform home of PROJECTS-01's codec)."""

from __future__ import annotations

import pytest

from aip.platform.http.cursor import CursorCodec, InvalidCursorError


def test_cursor_round_trips() -> None:
    codec = CursorCodec(b"k" * 32)
    data = {"sort": "name", "value": "Pump", "id": "0190a1b2-0000-7000-8000-000000000001"}
    assert codec.decode(codec.encode(data)) == data


def test_a_short_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 16 bytes"):
        CursorCodec(b"too-short")


def test_one_changed_byte_is_an_invalid_cursor() -> None:
    codec = CursorCodec(b"k" * 32)
    cursor = codec.encode({"sort": "name", "value": "Pump", "id": "x"})
    body, _, mac = cursor.partition(".")
    flipped = ("0" if body[0] != "0" else "1") + body[1:]  # change one byte of the body
    for bad in (f"{flipped}.{mac}", body, "not-base64!.x", "", cursor[:-2]):
        with pytest.raises(InvalidCursorError):
            codec.decode(bad)


def test_another_key_does_not_verify() -> None:
    codec = CursorCodec(b"k" * 32)
    cursor = codec.encode({"sort": "name", "value": "Pump", "id": "x"})
    with pytest.raises(InvalidCursorError):
        CursorCodec(b"other-key-of-32-bytes-0123456789").decode(cursor)
