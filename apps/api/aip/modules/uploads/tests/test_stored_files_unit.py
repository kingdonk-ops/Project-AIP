"""UPLOADS-08 unit tests: the generated-file id and input checks, and CSV keeping its type.

The input checks run before the connection is touched, so these need no database.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.uploads.pipeline.magic_bytes import check_magic_bytes
from aip.modules.uploads.stored_files import generated_file_id, store_generated_file

_T1 = UUID("00000000-0000-4000-8000-000000000001")
_T2 = UUID("00000000-0000-4000-8000-000000000002")
_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
_NO_CONN = cast(AsyncConnection, None)


def test_generated_file_id_is_stable_per_tenant_and_key() -> None:
    assert generated_file_id(_T1, "k") == generated_file_id(_T1, "k")
    assert generated_file_id(_T1, "k") != generated_file_id(_T2, "k")
    assert generated_file_id(_T1, "k") != generated_file_id(_T1, "k2")


@pytest.mark.parametrize(
    ("data", "content_type", "overrides"),
    [
        (b"", "application/pdf", {}),
        (b'<svg xmlns="http://www.w3.org/2000/svg"/>', "image/svg+xml", {}),
        (_PDF, "image/png", {}),
        (b"a,b\n\x00\x01\n", "text/csv", {}),
        (_PDF, "application/pdf", {"filename": "x" * 256}),
        (_PDF, "application/pdf", {"idempotency_key": ""}),
        (_PDF, "application/pdf", {"purpose": ""}),
    ],
)
async def test_store_generated_file_refuses_bad_input(
    data: bytes, content_type: str, overrides: dict[str, Any]
) -> None:
    kwargs: dict[str, Any] = {
        "data": data,
        "filename": "report.pdf",
        "content_type": content_type,
        "purpose": "report",
        "idempotency_key": "report-render:1",
        **overrides,
    }
    with pytest.raises(ValueError):
        await store_generated_file(_NO_CONN, **kwargs)


def test_a_clean_csv_keeps_its_declared_type() -> None:
    result = check_magic_bytes(b"Tag Number,Name\nKF-01,Pump\n", "text/csv")
    assert result.outcome == "pass"
    assert result.detail["detected"] == "text/csv"
