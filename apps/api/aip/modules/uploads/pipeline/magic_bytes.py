"""Stage (b): detect the real type from the leading bytes and check it against the declared one.

The filename and the declared MIME are never trusted for type (UPLOADS-01); here the *detected*
type (from the first 4 KB) must be allowed and compatible with the declared one. Text types must be
valid UTF-8 with no NUL bytes, and anything that is or looks like SVG or HTML fails outright.
"""

from __future__ import annotations

from ..platform_limits import DENIED_MIMES
from .types import StageResult

__all__ = ["HEAD_BYTES", "check_magic_bytes", "detect_mime"]

# UPLOADS-02 step 3b: the detector reads the first 4 KB.
HEAD_BYTES = 4096

# A *detected* ZIP container is legitimate for an OOXML file (the compatibility check below gates
# it), so the archive MIMEs in ``DENIED_MIMES`` — which deny a *declared* raw archive — are not
# dangerous on their own when detected. Everything else denied (executables, SVG, HTML, scripts)
# is dangerous the moment it is detected, whatever was declared.
_ARCHIVE_MIMES = frozenset(
    {
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
    }
)
_DANGEROUS_DETECTED = DENIED_MIMES - _ARCHIVE_MIMES

# Detected type -> the declared types it is compatible with. OOXML files are ZIP containers, so a
# declared xlsx/docx is compatible with a detected ``application/zip``.
_OOXML = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
_COMPATIBLE: dict[str, frozenset[str]] = {
    "image/jpeg": frozenset({"image/jpeg"}),
    "image/png": frozenset({"image/png"}),
    "image/webp": frozenset({"image/webp"}),
    "image/heic": frozenset({"image/heic"}),
    "application/pdf": frozenset({"application/pdf"}),
    "application/zip": _OOXML,
}


def _sniff_binary(head: bytes) -> str | None:
    """The detected MIME from a binary signature, or ``None`` when no signature matches."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "application/zip"
    if head.startswith((b"MZ",)):
        return "application/x-msdownload"
    if head.startswith(b"\x7fELF"):
        return "application/x-executable"
    if head[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"):
        return "application/x-mach-binary"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"mif1", b"heim"):
        return "image/heic"
    if head.startswith(b"GIF8"):
        return "image/gif"
    return None


def _looks_like_markup(head: bytes) -> bool:
    """True for bytes that begin (after optional BOM/whitespace) like SVG, HTML or XHTML."""
    try:
        start = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    except Exception:  # pragma: no cover - lstrip on bytes never raises
        return False
    return start.startswith((b"<?xml", b"<svg", b"<!doctype", b"<html"))


def detect_mime(head: bytes) -> str | None:
    """Detect the MIME from the leading bytes: a binary signature, markup, or ``None`` for text."""
    if _looks_like_markup(head):
        # Distinguish SVG (an XML image) from HTML only enough to deny both.
        return "image/svg+xml" if b"<svg" in head[:512].lower() else "text/html"
    return _sniff_binary(head)


def check_magic_bytes(head: bytes, declared_mime: str) -> StageResult:
    """Verify the detected type is allowed and compatible with ``declared_mime`` (step 3b)."""
    if declared_mime in DENIED_MIMES:
        return StageResult("magic_bytes", "fail", {"declared": declared_mime, "reason": "denied"})

    detected = detect_mime(head)
    if detected in _DANGEROUS_DETECTED:
        return StageResult("magic_bytes", "fail", {"detected": detected})

    if declared_mime in ("text/csv", "text/plain"):
        # No binary signature; it must be real text: valid UTF-8 with no NUL byte.
        if b"\x00" in head:
            return StageResult("magic_bytes", "fail", {"reason": "nul_byte"})
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            # A split multibyte run at the 4 KB boundary is not a failure; a genuine non-UTF-8
            # byte is. ``errors="strict"`` on the whole head would false-positive on the boundary,
            # so decode all but the last 3 bytes, which cannot hold a complete bad sequence alone.
            try:
                head[: max(0, len(head) - 3)].decode("utf-8")
            except UnicodeDecodeError:
                return StageResult("magic_bytes", "fail", {"reason": "not_utf8"})
        return StageResult("magic_bytes", "pass", {"detected": detected or "text/plain"})

    if detected is None:
        return StageResult("magic_bytes", "fail", {"detected": None, "declared": declared_mime})
    if declared_mime not in _COMPATIBLE.get(detected, frozenset()):
        return StageResult("magic_bytes", "fail", {"detected": detected, "declared": declared_mime})
    return StageResult("magic_bytes", "pass", {"detected": detected})
