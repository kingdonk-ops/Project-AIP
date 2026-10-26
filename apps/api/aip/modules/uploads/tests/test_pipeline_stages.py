"""UPLOADS-02 unit tests for the pure scan stages: magic bytes and the decompression/pixel caps."""

from __future__ import annotations

import struct

from aip.modules.uploads.pipeline.caps import (
    MAX_MEGAPIXELS,
    ZipEntry,
    evaluate_zip_entries,
    ratio_cap,
    size_cap,
)
from aip.modules.uploads.pipeline.magic_bytes import check_magic_bytes

GIB = 1024 * 1024 * 1024
MIB = 1024 * 1024

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    )


# --- magic bytes --------------------------------------------------------------------------------


def test_magic_bytes_executable_declared_as_jpeg_fails_with_detected() -> None:
    result = check_magic_bytes(b"MZ\x90\x00\x03\x00\x00\x00", "image/jpeg")
    assert result.outcome == "fail"
    assert result.detail["detected"] == "application/x-msdownload"


def test_magic_bytes_pdf_declared_as_pdf_passes() -> None:
    result = check_magic_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", "application/pdf")
    assert result.outcome == "pass"


def test_magic_bytes_ooxml_zip_container_is_compatible() -> None:
    assert check_magic_bytes(b"PK\x03\x04\x14\x00", XLSX_MIME).outcome == "pass"


def test_magic_bytes_html_bytes_named_jpeg_fails() -> None:
    result = check_magic_bytes(b"<!DOCTYPE html>\n<html><body>x", "image/jpeg")
    assert result.outcome == "fail"
    assert result.detail["detected"] == "text/html"


def test_magic_bytes_svg_is_denied() -> None:
    assert check_magic_bytes(b'<svg xmlns="http://www.w3.org/2000/svg">', "image/png").outcome == (
        "fail"
    )


def test_magic_bytes_csv_must_be_utf8_without_nul() -> None:
    assert check_magic_bytes("name,é\n1,2\n".encode(), "text/csv").outcome == "pass"
    assert check_magic_bytes(b"a,b\n\x00\x01\n", "text/csv").outcome == "fail"


# --- caps ---------------------------------------------------------------------------------------


def test_size_cap_rejects_over_declared_or_platform() -> None:
    assert size_cap(10, 20, 100).outcome == "pass"
    assert size_cap(21, 20, 100).outcome == "fail"
    assert size_cap(150, 200, 100).outcome == "fail"


def test_ratio_cap_png_over_one_hundred_megapixels_fails() -> None:
    result = ratio_cap(_png(20000, 20000), "image/png")
    assert result.outcome == "fail"
    assert result.detail["megapixels"] == 400


def test_ratio_cap_small_png_passes() -> None:
    result = ratio_cap(_png(800, 600), "image/png")
    assert result.outcome == "pass"
    assert result.detail["megapixels"] <= MAX_MEGAPIXELS


def test_zip_decompression_bomb_fails_on_ratio() -> None:
    result = evaluate_zip_entries([ZipEntry("xl/workbook.xml", GIB, MIB)])
    assert result.outcome == "fail"
    assert result.detail["ratio"] == 1024


def test_zip_path_traversal_fails() -> None:
    result = evaluate_zip_entries([ZipEntry("../../x", 10, 10)])
    assert result.outcome == "fail"
    assert result.detail["path"] == "../../x"


def test_zip_nested_archive_fails() -> None:
    result = evaluate_zip_entries([ZipEntry("payload.zip", 10, 10)])
    assert result.outcome == "fail"
    assert result.detail["nested"] == "payload.zip"
