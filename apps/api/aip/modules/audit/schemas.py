"""Pydantic models for the audit module (AUDIT-01).

``AuditEntryIn`` is the writer-side input: the business fields of one event. The chain writer
assigns ``seq``, ``prev_hash`` and ``hash``; callers never set those. ``asset_path``, ``source_ip``
and ``device`` are stored for querying but are **not** part of the hashed contract (see
``chain_hash``), so they can be corrected by a superseding entry without invalidating the chain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AuditEntryIn"]


class AuditEntryIn(BaseModel):
    """One audit event to append to a tenant's chain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str = Field(min_length=1)
    occurred_at: datetime
    actor_id: UUID | None = None
    on_behalf_of_id: UUID | None = None
    auth_strength: str | None = None
    source_module: str | None = None
    record_table: str | None = None
    record_id: UUID | None = None
    summary_key: str | None = None
    payload: dict[str, Any] | None = None
    reason_for_change: str | None = None
    flags: list[str] = Field(default_factory=list[str])
    project_id: UUID | None = None
    asset_id: UUID | None = None
    asset_path: str | None = None
    source_ip: str | None = None
    device: str | None = None
    source_event_id: UUID | None = None
    supersedes_id: UUID | None = None
