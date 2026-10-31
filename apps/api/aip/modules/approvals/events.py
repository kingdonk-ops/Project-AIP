"""Domain events approvals publishes (via the outbox, ADR 0003).

- ``workflow.transitioned`` v1: a transition took effect (APPROVALS-02). Payload
  ``{instanceId, recordType, recordId, projectId, from, to, action, actorId, definitionKey,
  definitionVersion}``. A decision left ``pending_countersign`` emits nothing; the countersign that
  applies it emits this event.
- ``workflow.definition_published`` v1: a draft became the active version
  ``{definitionId, key, version, recordType, projectId, previousDefinitionId}``.

Approval routes (APPROVALS-04), all on the ``workflow_instance`` aggregate:

- ``approval.requested`` v1: a step became ``pending`` ``{instanceId, stepId, recordType,
  recordId, projectId, approverType, approverRef, dueAt}``;
- ``approval.approved`` / ``approval.rejected`` v1: a route finished with that outcome, after its
  transition ``{instanceId, recordType, recordId, projectId, routeTemplateId, stepId, actorId,
  action}`` (``stepId`` and ``actorId`` are the last decision's);
- ``approval.completed`` v1: ``{instanceId, recordType, recordId, outcome}``, emitted after the
  outcome event in the same transaction.

The models are registered with the platform's event schemas when this module loads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = [
    "APPROVAL_APPROVED",
    "APPROVAL_COMPLETED",
    "APPROVAL_REJECTED",
    "APPROVAL_REQUESTED",
    "WORKFLOW_DEFINITION_PUBLISHED",
    "WORKFLOW_TRANSITIONED",
    "ApprovalCompleted",
    "ApprovalOutcome",
    "ApprovalRequested",
    "DefinitionPublished",
    "WorkflowTransitioned",
]

WORKFLOW_TRANSITIONED: Final = "workflow.transitioned"
WORKFLOW_DEFINITION_PUBLISHED: Final = "workflow.definition_published"
APPROVAL_REQUESTED: Final = "approval.requested"
APPROVAL_APPROVED: Final = "approval.approved"
APPROVAL_REJECTED: Final = "approval.rejected"
APPROVAL_COMPLETED: Final = "approval.completed"


class _Event(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class WorkflowTransitioned(_Event):
    instance_id: UUID
    record_type: str
    record_id: UUID
    project_id: UUID | None
    from_state: str = Field(alias="from")
    to_state: str = Field(alias="to")
    action: str
    actor_id: UUID | None
    definition_key: str
    definition_version: int


class DefinitionPublished(_Event):
    definition_id: UUID
    key: str
    version: int
    record_type: str
    project_id: UUID | None
    previous_definition_id: UUID | None


class ApprovalRequested(_Event):
    instance_id: UUID
    step_id: UUID
    record_type: str
    record_id: UUID
    project_id: UUID | None
    approver_type: Literal["user", "role", "team"]
    approver_ref: UUID
    due_at: datetime | None


class ApprovalOutcome(_Event):
    instance_id: UUID
    record_type: str
    record_id: UUID
    project_id: UUID | None
    route_template_id: UUID
    step_id: UUID
    actor_id: UUID | None
    action: str


class ApprovalCompleted(_Event):
    instance_id: UUID
    record_type: str
    record_id: UUID
    outcome: Literal["approved", "rejected"]


register_event(WORKFLOW_TRANSITIONED, 1, WorkflowTransitioned, "approvals")
register_event(WORKFLOW_DEFINITION_PUBLISHED, 1, DefinitionPublished, "approvals")
register_event(APPROVAL_REQUESTED, 1, ApprovalRequested, "approvals")
register_event(APPROVAL_APPROVED, 1, ApprovalOutcome, "approvals")
register_event(APPROVAL_REJECTED, 1, ApprovalOutcome, "approvals")
register_event(APPROVAL_COMPLETED, 1, ApprovalCompleted, "approvals")
