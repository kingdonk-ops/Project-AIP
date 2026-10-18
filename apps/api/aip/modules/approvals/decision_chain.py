"""The per-instance hash chain over ``workflow_decision_history`` (APPROVALS-02).

- ``entry_hash(entry)``: ``sha256`` (hex) of the RFC 8785 canonical JSON (sorted keys, no
  whitespace) of the entry's ``HASHED_FIELDS``. UUIDs are lower-case strings, timestamps are UTC
  ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` and an absent value is ``null``. Besides the spec's fields the
  hash covers the row's ``id``, ``supersedes_id``, ``status``, ``countersigns_id`` and sign-off
  assurance (ADR 0035), so no stored field can change unnoticed.
- ``genesis_hash(instance_id)``: the first entry's ``prev_hash``, ``sha256('genesis:' + id)``.
- ``verify_chain(entries)``: ``ChainOk`` or ``ChainBroken(broken_at_seq)`` for the first entry
  whose sequence, link or own hash does not hold.

Pure: no database, no clock. AUDIT-01's canonicaliser is not part of ``audit/api.py``, so this
uses the same ``rfc8785`` library directly and never touches the audit tables.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal
from uuid import UUID

import rfc8785

__all__ = [
    "HASHED_FIELDS",
    "ChainBroken",
    "ChainOk",
    "canonical_timestamp",
    "entry_hash",
    "genesis_hash",
    "sha256_hex",
    "verify_chain",
]

HASHED_FIELDS: Final = (
    "id",
    "tenant_id",
    "instance_id",
    "seq",
    "from_state",
    "to_state",
    "action",
    "actor_id",
    "on_behalf_of",
    "comment",
    "auth_strength",
    "ip_address",
    "guard_result",
    "step_id",
    "created_at",
    "prev_hash",
    "status",
    "countersigns_id",
    "assurance_level",
    "assurance_method",
    "authenticated_at",
    "device_id",
    "supersedes_id",
)


@dataclass(frozen=True, slots=True)
class ChainOk:
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class ChainBroken:
    broken_at_seq: int
    ok: Literal[False] = False


def sha256_hex(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def canonical_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps in the chain must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def genesis_hash(instance_id: UUID | str) -> str:
    return sha256_hex(f"genesis:{instance_id}")


def entry_hash(entry: Mapping[str, Any]) -> str:
    """The entry's hash over ``HASHED_FIELDS`` (a missing field hashes as ``null``)."""
    body = {name: _canonical(entry.get(name)) for name in HASHED_FIELDS}
    return sha256_hex(rfc8785.dumps(body))


def verify_chain(entries: Sequence[Mapping[str, Any]]) -> ChainOk | ChainBroken:
    """Check one instance's entries in ``seq`` order, starting from the genesis hash."""
    ordered = sorted(entries, key=lambda e: int(e["seq"]))
    previous: str | None = None
    for expected_seq, entry in enumerate(ordered, start=1):
        seq = int(entry["seq"])
        link = genesis_hash(entry["instance_id"]) if previous is None else previous
        if seq != expected_seq or entry.get("prev_hash") != link:
            return ChainBroken(seq)
        if entry.get("entry_hash") != entry_hash(entry):
            return ChainBroken(seq)
        previous = str(entry["entry_hash"])
    return ChainOk()
