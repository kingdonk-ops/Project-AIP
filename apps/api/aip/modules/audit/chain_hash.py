"""The audit hash-chain function (AUDIT-01).

This module is the tamper-evidence contract. The verifier (AUDIT-03) imports ``compute_hash`` and
``ChainEntry`` unchanged and must reproduce byte-for-byte the hashes the writer stored, so nothing
here may ever change in a way that alters an output for an existing input. ``HASH_SPEC_VERSION``
is bumped only by a deliberate, migrated re-hash.

The hash of an entry is::

    hash = sha256( prev_hash || JCS(entry) )

where ``prev_hash`` is the 32-byte hash of the previous entry in the same ``(tenant, stream)``
chain (the genesis predecessor is 32 zero bytes, ``GENESIS_PREV_HASH``) and ``JCS(entry)`` is the
RFC 8785 JSON Canonicalisation Scheme serialisation of a JSON object built from this fixed,
ordered field list (the contract):

    tenant_id, stream, seq, occurred_at, actor_id, on_behalf_of_id, auth_strength, source_module,
    record_table, record_id, event_type, summary_key, payload, reason_for_change, flags, project_id,
    asset_id, source_event_id, supersedes_id

JCS sorts object keys, so the field order above is documentation; what is fixed is the *set* of
fields and how each is rendered:

- UUIDs are lower-case canonical strings; an absent (``None``) value is JSON ``null``.
- ``seq`` is a JSON number.
- ``occurred_at`` is ISO-8601 in UTC with exactly six fractional-second digits and a ``Z`` suffix,
  e.g. ``2026-10-07T01:02:03.000004Z``.
- ``payload`` is the before/after object verbatim; because JCS sorts keys recursively, re-ordering
  its keys does not change the hash, but changing any value does.
- ``flags`` is sorted ascending, so flag order never affects the hash.

The only dependencies are :mod:`hashlib` and the ``rfc8785`` canonicaliser. It must not import
``aip.platform`` or any other module (an import-linter contract enforces this), so the writer and
an offline verifier share exactly the same code with no platform coupling.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

__all__ = [
    "GENESIS_PREV_HASH",
    "HASH_SPEC_VERSION",
    "ChainEntry",
    "canonical_timestamp",
    "compute_hash",
]

HASH_SPEC_VERSION = 1
"""The version of the field list and rendering rules above. Stored alongside the chain."""

GENESIS_PREV_HASH = b"\x00" * 32
"""The predecessor hash of the first entry (``seq = 1``) in every chain: 32 zero bytes."""

_HASH_SIZE = 32

# The fixed field list (the hashed contract). Order is documentation only (JCS sorts keys), but the
# set is frozen: adding, removing or renaming a field changes every hash and needs a spec bump.
FIELDS: tuple[str, ...] = (
    "tenant_id",
    "stream",
    "seq",
    "occurred_at",
    "actor_id",
    "on_behalf_of_id",
    "auth_strength",
    "source_module",
    "record_table",
    "record_id",
    "event_type",
    "summary_key",
    "payload",
    "reason_for_change",
    "flags",
    "project_id",
    "asset_id",
    "source_event_id",
    "supersedes_id",
)


@dataclass(frozen=True, slots=True)
class ChainEntry:
    """The hashed fields of one audit entry (a value object, independent of storage).

    ``seq`` and ``prev_hash`` are assigned by the chain writer; everything else comes from the
    event. The repository builds one of these per row and feeds it to :func:`compute_hash`.
    """

    tenant_id: UUID
    stream: str
    seq: int
    occurred_at: datetime
    event_type: str
    actor_id: UUID | None = None
    on_behalf_of_id: UUID | None = None
    auth_strength: str | None = None
    source_module: str | None = None
    record_table: str | None = None
    record_id: UUID | None = None
    summary_key: str | None = None
    payload: Mapping[str, Any] | None = None
    reason_for_change: str | None = None
    flags: Sequence[str] = ()
    project_id: UUID | None = None
    asset_id: UUID | None = None
    source_event_id: UUID | None = None
    supersedes_id: UUID | None = None


def canonical_timestamp(value: datetime) -> str:
    """ISO-8601 UTC with exactly six fractional digits and ``Z`` (``2026-10-07T01:02:03.000004Z``).

    ``value`` must be timezone-aware; it is converted to UTC first so the same instant always
    renders identically regardless of the caller's zone.
    """
    if value.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")
    utc = value.astimezone(UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond:06d}Z"


def _uuid(value: UUID | None) -> str | None:
    return None if value is None else str(value).lower()


def canonical_object(entry: ChainEntry) -> dict[str, Any]:
    """The JSON object hashed for ``entry`` (before canonicalisation). Exposed for tests/tools."""
    return {
        "tenant_id": _uuid(entry.tenant_id),
        "stream": entry.stream,
        "seq": entry.seq,
        "occurred_at": canonical_timestamp(entry.occurred_at),
        "actor_id": _uuid(entry.actor_id),
        "on_behalf_of_id": _uuid(entry.on_behalf_of_id),
        "auth_strength": entry.auth_strength,
        "source_module": entry.source_module,
        "record_table": entry.record_table,
        "record_id": _uuid(entry.record_id),
        "event_type": entry.event_type,
        "summary_key": entry.summary_key,
        "payload": dict(entry.payload) if entry.payload is not None else None,
        "reason_for_change": entry.reason_for_change,
        "flags": sorted(entry.flags),
        "project_id": _uuid(entry.project_id),
        "asset_id": _uuid(entry.asset_id),
        "source_event_id": _uuid(entry.source_event_id),
        "supersedes_id": _uuid(entry.supersedes_id),
    }


def compute_hash(prev_hash: bytes, entry: ChainEntry) -> bytes:
    """``sha256(prev_hash || JCS(entry))`` as 32 raw bytes.

    ``prev_hash`` is the previous entry's 32-byte hash, or :data:`GENESIS_PREV_HASH` for ``seq=1``.
    """
    import rfc8785  # local import keeps module import cost off the verifier's cold path

    if len(prev_hash) != _HASH_SIZE:
        raise ValueError(f"prev_hash must be {_HASH_SIZE} bytes, got {len(prev_hash)}")
    canonical = rfc8785.dumps(canonical_object(entry))
    return hashlib.sha256(prev_hash + canonical).digest()
