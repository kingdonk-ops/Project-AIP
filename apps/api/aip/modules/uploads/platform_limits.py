"""Hard platform ceilings for uploads (UPLOADS-01).

These are the non-negotiable limits the signed presign policy enforces. UPLOADS-05 adds per-type
policy rows that may *narrow* them (never widen), so a tenant admin can forbid a type or set a
smaller cap, but can never allow a denied type or raise a size above the ceilings here.

``filename`` is display-only and never consulted: the declared MIME is checked here and the
*detected* type (magic bytes) is re-checked after upload in UPLOADS-02.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ALLOWED_MIMES",
    "DENIED_MIMES",
    "PRESIGN_TTL_S",
    "SINGLE_PART_MAX_BYTES",
    "classify_declared",
    "is_allowed_type",
]

# A single-part presigned POST tops out at 100 MiB; a larger declared size must use multipart
# (UPLOADS-03), signalled to the client as 413 USE_MULTIPART.
SINGLE_PART_MAX_BYTES: Final = 100 * 1024 * 1024  # 104857600

# The presigned POST lives for 15 minutes (the session TTL), well inside S3's one-week ceiling.
PRESIGN_TTL_S: Final = 15 * 60  # 900

# The declared-type allow-list. Anything outside it is rejected as UNSUPPORTED_TYPE; the detected
# type is re-validated against magic bytes after upload (UPLOADS-02).
ALLOWED_MIMES: Final[frozenset[str]] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/webp",
        "application/pdf",
        "text/csv",
        "text/plain",
        # OOXML (xlsx, docx)
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

# Types that are always denied, even if a later policy row tried to allow them. The allow-list
# already excludes them; this set documents the intent and guards against a widened allow-list.
DENIED_MIMES: Final[frozenset[str]] = frozenset(
    {
        "image/svg+xml",
        "text/html",
        "application/xhtml+xml",
        "application/javascript",
        "application/x-javascript",
        "text/javascript",
        # executables
        "application/x-msdownload",
        "application/x-executable",
        "application/x-mach-binary",
        "application/vnd.microsoft.portable-executable",
        # archives (decompression-bomb surface; handled only by deeper scanning later)
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
    }
)

assert ALLOWED_MIMES.isdisjoint(DENIED_MIMES), "a MIME type cannot be both allowed and denied"


def is_allowed_type(declared_mime: str) -> bool:
    """Whether ``declared_mime`` may be uploaded at all (allow-list, denials win)."""
    return declared_mime in ALLOWED_MIMES and declared_mime not in DENIED_MIMES


def classify_declared(declared_mime: str, size_bytes: int) -> str | None:
    """Return a refusal ``code`` for the declared type/size, or ``None`` when it is acceptable.

    Codes: ``INVALID_SIZE`` (empty/negative), ``UNSUPPORTED_TYPE`` (not on the allow-list),
    ``USE_MULTIPART`` (over the single-part ceiling). Size is checked first so a zero-byte upload
    is always ``INVALID_SIZE``; the type is checked before the multipart ceiling so a denied type
    never looks like a "just use multipart" case.
    """
    if size_bytes <= 0:
        return "INVALID_SIZE"
    if not is_allowed_type(declared_mime):
        return "UNSUPPORTED_TYPE"
    if size_bytes > SINGLE_PART_MAX_BYTES:
        return "USE_MULTIPART"
    return None
