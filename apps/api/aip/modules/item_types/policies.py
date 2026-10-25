"""Limits and lifecycle rules for item_types (ITEMTYPES-01).

Authorisation itself goes through the policy service (``requires`` on every route) and RLS; this
module holds only the per-tenant caps, small enough that lists are returned whole.
"""

from __future__ import annotations

from typing import Final

__all__ = ["MAX_CATEGORIES_PER_CONTENT_TYPE", "MAX_CONTENT_TYPES", "MAX_ITEM_TYPES"]

MAX_CONTENT_TYPES: Final = 50
MAX_CATEGORIES_PER_CONTENT_TYPE: Final = 200
MAX_ITEM_TYPES: Final = 1000
