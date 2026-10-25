"""Stages (a) size cap and (c) decompression / pixel caps (UPLOADS-02 step 3).

Caps are read from headers only, never by expanding the object: image dimensions from the header,
and a ZIP-based OOXML file's declared sizes from its central directory. A decompression bomb, an
over-large image, a zip with too many entries, a nested archive or a traversing path all fail.
"""

from __future__ import annotations

import io
import struct
import zipfile
from dataclasses import dataclass

from .types import StageResult

__all__ = [
    "MAX_MEGAPIXELS",
    "MAX_RATIO",
    "MAX_ZIP_ENTRIES",
    "ZipEntry",
    "evaluate_zip_entries",
    "image_dimensions",
    "ratio_cap",
    "read_zip_entries",
    "size_cap",
]

MAX_MEGAPIXELS = 100
MAX_RATIO = 100
MAX_ZIP_ENTRIES = 10_000
_NESTED_ARCHIVE_SUFFIXES = (".zip", ".gz", ".tar", ".7z", ".rar", ".bz2", ".xz")


def size_cap(actual_size: int, declared_size: int, platform_max: int) -> StageResult:
    """(a) The streamed size is at most the declared size and the platform ceiling."""
    if actual_size > declared_size or actual_size > platform_max:
        return StageResult(
            "size_cap",
            "fail",
            {"actual": actual_size, "declared": declared_size, "platform_max": platform_max},
        )
    return StageResult("size_cap", "pass", {"actual": actual_size})


# --- images ------------------------------------------------------------------------------------


def image_dimensions(head: bytes, detected_mime: str) -> tuple[int, int] | None:
    """(width, height) from a PNG or JPEG header, or ``None`` when it cannot be read."""
    if detected_mime == "image/png" and head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
        width, height = struct.unpack(">II", head[16:24])
        return int(width), int(height)
    if detected_mime == "image/jpeg":
        return _jpeg_dimensions(head)
    return None


def _jpeg_dimensions(head: bytes) -> tuple[int, int] | None:
    i = 2  # skip the SOI marker
    n = len(head)
    while i + 9 < n and head[i] == 0xFF:
        marker = head[i + 1]
        # Start-of-frame markers carry the dimensions; others carry a length we skip over.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", head[i + 5 : i + 9])
            return int(width), int(height)
        segment_len = struct.unpack(">H", head[i + 2 : i + 4])[0]
        i += 2 + segment_len
    return None


# --- OOXML / zip central directory ---------------------------------------------------------------


@dataclass(frozen=True)
class ZipEntry:
    """One central-directory entry's declared name and sizes."""

    name: str
    uncompressed: int
    compressed: int


def read_zip_entries(data: bytes) -> list[ZipEntry]:
    """Read the central directory only (never expands an entry)."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return [ZipEntry(i.filename, i.file_size, i.compress_size) for i in zf.infolist()]


def _traverses(name: str) -> bool:
    """A path that is absolute or climbs out of the archive root."""
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return True
    return any(part == ".." for part in name.replace("\\", "/").split("/"))


def evaluate_zip_entries(entries: list[ZipEntry]) -> StageResult:
    """(c) The central directory passes the decompression, count, nesting and path checks."""
    if len(entries) > MAX_ZIP_ENTRIES:
        return StageResult("ratio_cap", "fail", {"entries": len(entries)})
    total_uncompressed = sum(e.uncompressed for e in entries)
    total_compressed = sum(e.compressed for e in entries)
    for entry in entries:
        if _traverses(entry.name):
            return StageResult("ratio_cap", "fail", {"path": entry.name})
        if entry.name.lower().endswith(_NESTED_ARCHIVE_SUFFIXES):
            return StageResult("ratio_cap", "fail", {"nested": entry.name})
    if total_compressed > 0:
        ratio = total_uncompressed // total_compressed
        if ratio > MAX_RATIO:
            return StageResult("ratio_cap", "fail", {"ratio": ratio})
    return StageResult("ratio_cap", "pass", {"entries": len(entries)})


def ratio_cap(data: bytes, detected_mime: str) -> StageResult:
    """(c) Dispatch to the image or ZIP check by detected type; other types pass this stage."""
    if detected_mime in ("image/png", "image/jpeg"):
        dims = image_dimensions(data, detected_mime)
        if dims is None:
            return StageResult("ratio_cap", "fail", {"reason": "unreadable_dimensions"})
        megapixels = (dims[0] * dims[1]) // 1_000_000
        if megapixels > MAX_MEGAPIXELS:
            return StageResult(
                "ratio_cap", "fail", {"megapixels": megapixels, "width": dims[0], "height": dims[1]}
            )
        return StageResult("ratio_cap", "pass", {"megapixels": megapixels})
    if detected_mime == "application/zip":
        return evaluate_zip_entries(read_zip_entries(data))
    return StageResult("ratio_cap", "pass", {})
