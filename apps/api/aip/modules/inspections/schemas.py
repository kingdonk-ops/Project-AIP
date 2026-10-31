"""Pydantic request/response models for inspections (INSPECTIONS-01).

JSON is camelCase (``assetId``, ``templateRevisionId``). Requests forbid unknown keys, so a client
cannot send ``state``, ``source`` or ``sourceRefId`` (422): the server sets them. Responses carry
codes and term keys, never display text; a kind's label is ``inspection.kind.<code>`` and a
source's ``inspection.source.<code>``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    "KINDS",
    "SOURCES",
    "AvailableTransition",
    "DecisionOut",
    "InspectionCreate",
    "InspectionDetail",
    "InspectionErrorBody",
    "InspectionHistory",
    "InspectionKind",
    "InspectionOut",
    "InspectionPage",
    "InspectionSource",
    "InspectionTransitionOut",
    "TransitionBody",
]

InspectionKind = Literal["inspection", "itp", "rfi"]
InspectionSource = Literal["manual", "scope_task", "reinspection", "import"]
KINDS: tuple[str, ...] = ("inspection", "itp", "rfi")
SOURCES: tuple[str, ...] = ("manual", "scope_task", "reinspection", "import")

Comment = Annotated[str, Field(max_length=4000)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response: built from database rows, so columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class InspectionErrorBody(_Out):
    """A domain error: a stable ``code`` (``ASSET_NOT_FOUND``, ``NOT_COMPLETED``, ...) and the
    term key of its message when there is one."""

    code: str
    message_key: str | None = None


class InspectionCreate(_Model):
    """``POST /inspections``. Without ``templateRevisionId`` the template's current published
    revision is pinned; with it, that published revision of ``templateId``."""

    asset_id: UUID
    project_id: UUID | None = None
    template_id: UUID
    template_revision_id: UUID | None = None
    kind: InspectionKind
    client_generated_id: UUID | None = None


class TransitionBody(_Model):
    action: Annotated[str, Field(min_length=1, max_length=100)]
    comment: Comment | None = None
    expected_sync_version: int | None = Field(default=None, ge=1)


class InspectionOut(_Out):
    id: UUID
    asset_id: UUID
    project_id: UUID | None
    template_id: UUID
    template_revision_id: UUID
    kind: InspectionKind
    source: InspectionSource
    source_ref_id: UUID | None
    itp_parent_id: UUID | None
    workflow_instance_id: UUID
    state: str
    created_by: UUID
    client_generated_id: UUID | None
    sync_version: int
    created_at: datetime
    updated_at: datetime


class AvailableTransition(_Out):
    action: str
    to_state: str
    label_key: str
    critical: bool
    requires_comment: bool
    allowed: bool
    reason_key: str | None


class InspectionDetail(InspectionOut):
    """The record plus its workflow: ``currentState`` is the instance's (the truth), and
    ``instanceSyncVersion`` the value a transition may send as ``expectedSyncVersion``."""

    current_state: str
    instance_sync_version: int
    pending_countersign: str | None
    available_transitions: list[AvailableTransition]


class DecisionOut(_Out):
    id: UUID
    seq: int
    from_state: str
    to_state: str
    action: str
    actor_id: UUID | None
    comment: str | None
    auth_strength: str
    status: str
    guard_result: dict[str, Any] | None
    prev_hash: str
    entry_hash: str
    created_at: datetime


class InspectionTransitionOut(_Out):
    """200 when the transition took effect, 202 when it waits for a countersign."""

    inspection: InspectionDetail
    decision: DecisionOut


class InspectionHistory(_Out):
    entries: list[DecisionOut]
    chain_valid: bool
    broken_at_seq: int | None = None


class InspectionPage(_Out):
    items: list[InspectionOut]
    next_cursor: str | None
