"""Tenant-scoped object keys (STACK-02, ADR 0006).

Every object key is built here as ``tenant/<uuid>/<parts...>``. The prefix is a second isolation
layer next to the per-tenant KMS key, so no caller may build keys by hand.
"""

from __future__ import annotations

import uuid
from typing import NewType

ObjectKey = NewType("ObjectKey", str)
"""An object key built by :func:`tenant_key`. ``ObjectStore`` methods accept only this type."""

_FORBIDDEN_CHARS = ("\\", "\x00")


def tenant_key(tenant_id: uuid.UUID | str, *parts: str) -> ObjectKey:
    """Return ``tenant/<tenant_id>/<parts...>``.

    A part may contain ``/`` to add several segments. Raises ``ValueError`` for a tenant id that is
    not a UUID, no parts, a leading ``/``, or any empty, ``.`` or ``..`` segment, backslash or NUL.
    """
    tenant = tenant_id if isinstance(tenant_id, uuid.UUID) else _parse_uuid(tenant_id)
    if not parts:
        raise ValueError("tenant_key needs at least one part after the tenant id")
    segments: list[str] = []
    for part in parts:
        if part.startswith("/"):
            raise ValueError(f"object key part must not start with '/': {part!r}")
        if any(ch in part for ch in _FORBIDDEN_CHARS):
            raise ValueError(f"object key part contains a forbidden character: {part!r}")
        for segment in part.split("/"):
            if segment in ("", ".", ".."):
                raise ValueError(f"object key part has an empty, '.' or '..' segment: {part!r}")
            segments.append(segment)
    return ObjectKey("/".join(("tenant", str(tenant), *segments)))


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise ValueError(f"tenant id is not a UUID: {value!r}") from None
    if str(parsed) != value.lower():
        raise ValueError(f"tenant id is not a canonical UUID: {value!r}")
    return parsed
