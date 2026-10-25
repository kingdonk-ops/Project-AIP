"""Pure asset rules (ASSETS-01): the derived internal tag and Tag Number normalisation.

No database or request context here, so both are trivially unit-testable (ADR 0004).
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

__all__ = ["internal_tag", "normalise_tag_number"]

# Crockford base32 (no I, L, O or U): a transcription-proof alphabet for the human-visible tag.
_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LOW_BITS: Final = 60  # 12 base32 characters, grouped 4-4-4


def internal_tag(asset_id: UUID) -> str:
    """``AT-XXXX-XXXX-XXXX`` from the id's low 60 bits (UUIDv7 low bits are random).

    Stable for a given id and unique in practice; the per-tenant unique index is the real guard.
    """
    low = asset_id.int & ((1 << _LOW_BITS) - 1)
    digits = [_CROCKFORD[(low >> shift) & 0x1F] for shift in range(_LOW_BITS - 5, -1, -5)]
    body = "".join(digits)
    return f"AT-{body[0:4]}-{body[4:8]}-{body[8:12]}"


def normalise_tag_number(value: str | None) -> str | None:
    """Trim, collapse inner whitespace to single spaces; an empty result becomes ``None``."""
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None
