"""Pydantic request/response models for inspections (INSPECTIONS-01) and responses (INSPECTIONS-02).

JSON is camelCase (``assetId``, ``templateRevisionId``). Requests forbid unknown keys, so a client
cannot send ``state``, ``source`` or ``sourceRefId`` (422): the server sets them. Responses carry
codes and term keys, never display text; a kind's label is ``inspection.kind.<code>`` and a
source's ``inspection.source.<code>``. An answer body has no ``failed``: the server decides it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.alias_generators import to_camel

__all__ = [
    "FIELD_KEY_PATTERN",
    "KINDS",
    "SOURCES",
    "AnswerIn",
    "AnswerOut",
    "AnswersEvaluation",
    "CurrentResponses",
    "InspectionAvailableTransition",
    "InspectionCreate",
    "InspectionDecision",
    "InspectionDetail",
    "InspectionErrorBody",
    "InspectionHistory",
    "InspectionKind",
    "InspectionOut",
    "InspectionPage",
    "InspectionSource",
    "InspectionTransitionOut",
    "ResponseEntry",
    "ResponseHistory",
    "ResponseResult",
    "ResponsesIn",
    "ResponsesOut",
    "TransitionBody",
]

InspectionKind = Literal["inspection", "itp", "rfi"]
InspectionSource = Literal["manual", "scope_task", "reinspection", "import"]
KINDS: tuple[str, ...] = ("inspection", "itp", "rfi")
SOURCES: tuple[str, ...] = ("manual", "scope_task", "reinspection", "import")

Comment = Annotated[str, Field(max_length=4000)]

FIELD_KEY_PATTERN = r"^[a-z][a-z0-9_]{0,62}$"  # the form field key rule (and the column CHECK)
FieldKey = Annotated[str, Field(pattern=FIELD_KEY_PATTERN)]


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


class InspectionAvailableTransition(_Out):
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
    available_transitions: list[InspectionAvailableTransition]


class InspectionDecision(_Out):
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
    decision: InspectionDecision


class InspectionHistory(_Out):
    entries: list[InspectionDecision]
    chain_valid: bool
    broken_at_seq: int | None = None


class InspectionPage(_Out):
    items: list[InspectionOut]
    next_cursor: str | None


# --- responses (INSPECTIONS-02) ----------------------------------------------------------------


class AnswerIn(_Model):
    """One answer; ``value`` ``null`` clears it. ``clientId`` makes a retry idempotent."""

    field_key: FieldKey
    value: JsonValue
    client_id: UUID


class ResponsesIn(_Model):
    """``POST /inspections/{id}/responses``: 1 to 200 answers, each field and client id once."""

    answers: Annotated[list[AnswerIn], Field(min_length=1, max_length=200)]


class ResponseResult(_Out):
    """``created`` is false for a ``clientId`` already stored (the first response is returned)."""

    client_id: UUID
    response_id: UUID
    created: bool
    failed: bool


class ResponsesOut(_Out):
    results: list[ResponseResult]


class AnswerOut(_Out):
    value: JsonValue
    failed: bool
    responded_by: UUID
    responded_at: datetime
    response_id: UUID


class AnswersEvaluation(_Out):
    """The FORMS-02 evaluation of the current answers: ``missingRequired`` lists the visible
    required fields with no answer, ``failed`` the fields whose answer fails."""

    visible: dict[str, bool]
    required: dict[str, bool]
    missing_required: list[str]
    failed: list[str]


class CurrentResponses(_Out):
    """The current answer per field and the evaluation of those answers."""

    answers: dict[str, AnswerOut]
    evaluation: AnswersEvaluation


class ResponseEntry(_Out):
    id: UUID
    field_key: str
    value: JsonValue
    failed: bool
    revision_id: UUID
    client_id: UUID
    supersedes_id: UUID | None
    responded_by: UUID
    responded_at: datetime


class ResponseHistory(_Out):
    """Every response for one field, oldest first."""

    entries: list[ResponseEntry]
