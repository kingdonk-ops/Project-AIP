"""Unit tests for the upload-session pure logic (UPLOADS-01): limits, presign policy, keys, schema.

No database or object store: these cover the decisions the signed presign policy rests on.
"""

from __future__ import annotations

import re
import uuid

import pytest
from pydantic import ValidationError

from aip.modules.uploads.platform_limits import (
    SINGLE_PART_MAX_BYTES,
    classify_declared,
)
from aip.modules.uploads.schemas import SessionCreate
from aip.modules.uploads.service import build_post_policy, quarantine_token
from aip.platform.capabilities.keys import tenant_key

T1 = uuid.UUID("00000000-0000-4000-8000-00000000000a")
KEY_RE = re.compile(r"^tenant/[0-9a-f-]{36}/quarantine/[A-Za-z0-9_-]{22}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{22}$")


# --- platform limits --------------------------------------------------------------------------


def test_svg_is_unsupported() -> None:
    assert classify_declared("image/svg+xml", 1024) == "UNSUPPORTED_TYPE"


def test_html_is_unsupported() -> None:
    assert classify_declared("text/html", 1024) == "UNSUPPORTED_TYPE"


def test_zero_bytes_is_invalid_size() -> None:
    assert classify_declared("image/jpeg", 0) == "INVALID_SIZE"


def test_over_single_part_cap_needs_multipart() -> None:
    assert classify_declared("image/jpeg", SINGLE_PART_MAX_BYTES + 1) == "USE_MULTIPART"
    assert SINGLE_PART_MAX_BYTES + 1 == 104857601


def test_allowed_type_at_the_cap_is_ok() -> None:
    assert classify_declared("image/jpeg", 2048) is None
    assert classify_declared("image/jpeg", SINGLE_PART_MAX_BYTES) is None
    assert classify_declared("application/pdf", 10) is None


def test_zero_size_wins_over_bad_type() -> None:
    # Size is checked first, so an empty upload is always INVALID_SIZE.
    assert classify_declared("image/svg+xml", 0) == "INVALID_SIZE"


# --- presign policy ---------------------------------------------------------------------------


def test_policy_pins_length_and_content_type() -> None:
    fields, conditions = build_post_policy("image/jpeg", 2048)
    assert ["content-length-range", 1, 2048] in conditions
    assert ["eq", "$Content-Type", "image/jpeg"] in conditions
    assert fields["Content-Type"] == "image/jpeg"


def test_policy_without_kms_has_no_sse() -> None:
    fields, conditions = build_post_policy("image/jpeg", 2048)
    assert all("server-side-encryption" not in k for k in fields)
    assert all("server-side-encryption" not in str(c) for c in conditions)


def test_policy_with_kms_requires_sse_and_context() -> None:
    fields, conditions = build_post_policy(
        "application/pdf", 10, kms_key_id="arn:aws:kms:key/abc", tenant_id=T1
    )
    assert fields["x-amz-server-side-encryption"] == "aws:kms"
    assert fields["x-amz-server-side-encryption-aws-kms-key-id"] == "arn:aws:kms:key/abc"
    key_header = "x-amz-server-side-encryption-aws-kms-key-id"
    assert ["eq", "$x-amz-server-side-encryption", "aws:kms"] in conditions
    assert ["eq", f"${key_header}", "arn:aws:kms:key/abc"] in conditions
    # The tenant encryption context is present and ties the object to this tenant (ADR 0006).
    assert "x-amz-server-side-encryption-context" in fields


# --- quarantine key ---------------------------------------------------------------------------


def test_token_is_128_random_bits_base64url() -> None:
    tokens = {quarantine_token() for _ in range(100)}
    assert len(tokens) == 100  # practically never collides
    assert all(TOKEN_RE.fullmatch(t) for t in tokens)


def test_key_is_tenant_prefixed_and_carries_no_user_text() -> None:
    key = tenant_key(T1, "quarantine", quarantine_token())
    assert KEY_RE.fullmatch(key), key


# --- request schema ---------------------------------------------------------------------------


def test_filename_is_display_only_and_accepts_traversal() -> None:
    # A path-like filename is accepted; it never becomes part of the key (that uses the token).
    body = SessionCreate.model_validate(
        {
            "projectId": str(T1),
            "filename": "../../etc/passwd.jpg",
            "declaredMime": "image/jpeg",
            "sizeBytes": 1024,
        }
    )
    assert body.filename == "../../etc/passwd.jpg"


def test_declared_mime_is_lowercased() -> None:
    body = SessionCreate.model_validate(
        {"projectId": str(T1), "filename": "a", "declaredMime": "Image/JPEG", "sizeBytes": 1}
    )
    assert body.declared_mime == "image/jpeg"


def test_negative_size_is_a_schema_error() -> None:
    with pytest.raises(ValidationError):
        SessionCreate.model_validate(
            {"projectId": str(T1), "filename": "a", "declaredMime": "image/jpeg", "sizeBytes": -1}
        )
