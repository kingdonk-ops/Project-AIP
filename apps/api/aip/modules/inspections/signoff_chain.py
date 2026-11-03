"""The per-inspection hash chain over ``inspection_signoffs`` (INSPECTIONS-03, ADR 0035 §5).

- ``entry_hash(entry)``: ``sha256`` (hex) of the RFC 8785 canonical JSON (sorted keys, no
  whitespace) of every stored column except ``entry_hash`` and ``created_at``. UUIDs are lower-case
  strings, timestamps UTC ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` and an absent value ``null``.
- ``genesis_hash(inspection_id)``: the first entry's ``prev_hash``, ``sha256('genesis:' + id)``.
- ``verify_chain(entries)``: ``ChainOk`` or ``ChainBroken(broken_at_seq)`` for the first entry
  whose sequence, link or own hash does not hold.
- ``content_hash(...)``: what was signed, ``sha256`` of canonical
  ``{inspectionId, templateRevisionId, stepId, answers}`` with ``answers`` the current value per
  field key.

Pure: no database, no clock. It mirrors approvals' ``decision_chain`` with the same ``rfc8785``
library rather than importing it (approvals offers only its ``api.py``).
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
    "content_hash",
    "entry_hash",
    "genesis_hash",
    "verify_chain",
]

HASHED_FIELDS: Final = (
    "id",
    "tenant_id",
    "inspection_id",
    "itp_step_id",
    "asset_id",
    "seq",
    "signatory_role",
    "signer_user_id",
    "decision",
    "action_code",
    "status",
    "countersigns_id",
    "auth_strength",
    "assurance_level",
    "assurance_method",
    "authenticated_at",
    "device_id",
    "eligibility_result",
    "content_hash",
    "prev_hash",
    "comment",
    "signed_at",
)


@dataclass(frozen=True, slots=True)
class ChainOk:
    ok: Literal[True] = True


@dataclass(frozen=True, slots=True)
class ChainBroken:
    broken_at_seq: int
    ok: Literal[False] = False


def _sha256_hex(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _canonical(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamps in the chain must be timezone-aware")
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def genesis_hash(inspection_id: UUID | str) -> str:
    return _sha256_hex(f"genesis:{inspection_id}")


def entry_hash(entry: Mapping[str, Any]) -> str:
    """The entry's hash over ``HASHED_FIELDS`` (a missing field hashes as ``null``)."""
    body = {name: _canonical(entry.get(name)) for name in HASHED_FIELDS}
    return _sha256_hex(rfc8785.dumps(body))


def content_hash(
    inspection_id: UUID,
    template_revision_id: UUID,
    step_id: UUID | None,
    answers: Mapping[str, Any],
) -> str:
    """The hash of what a sign-off covers: the step and the inspection's current answers."""
    body = {
        "inspectionId": str(inspection_id),
        "templateRevisionId": str(template_revision_id),
        "stepId": None if step_id is None else str(step_id),
        "answers": _canonical(answers),
    }
    return _sha256_hex(rfc8785.dumps(body))


def verify_chain(entries: Sequence[Mapping[str, Any]]) -> ChainOk | ChainBroken:
    """Check one inspection's entries in ``seq`` order, starting from the genesis hash."""
    ordered = sorted(entries, key=lambda e: int(e["seq"]))
    previous: str | None = None
    for expected_seq, entry in enumerate(ordered, start=1):
        seq = int(entry["seq"])
        link = genesis_hash(entry["inspection_id"]) if previous is None else previous
        if seq != expected_seq or entry.get("prev_hash") != link:
            return ChainBroken(seq)
        if entry.get("entry_hash") != entry_hash(entry):
            return ChainBroken(seq)
        previous = str(entry["entry_hash"])
    return ChainOk()
