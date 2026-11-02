"""Domain events the inspections module publishes and consumes (via the outbox, ADR 0003).

- ``inspection.created`` v1 ``{inspectionId, assetId, projectId, kind, templateRevisionId,
  source}``: emitted in the create's transaction.
- ``inspection.answer_failed`` v1 ``{inspectionId, responseId, fieldKey, assetId, projectId}``
  (INSPECTIONS-02): an answer newly failed its field's ``failWhen`` (the field's previous answer was
  absent or passed). Emitted in the submit's transaction; ISSUES-02 raises issues from it.
- ``inspection.state_changed`` v1 ``{inspectionId, assetId, projectId, from, to, action}``: an
  applied transition moved the inspection's lifecycle. Emitted in the transition's transaction when
  it went through ``/api/v1/inspections``, else by :func:`follow_workflow` below.
- ``itp_step.released`` v1 ``{stepId, inspectionId, assetId, projectId, pointType, decision,
  taskId, blocksTaskId, releasedAt}`` (INSPECTIONS-03): an ITP step was released or waived, in the
  sign-off's transaction. SCOPEWORK-03 unblocks the step's ``blocksTaskId`` from it.
- ``itp_step.hold_changed`` v1 ``{stepId, inspectionId, issueId, held}`` (INSPECTIONS-03): an
  issues NCR placed or cleared its hold on a step.

``follow_workflow`` subscribes to approvals' ``workflow.transitioned`` v1: for an ``inspection``
record whose cached ``state`` differs from its instance's ``current_state`` it updates the cache and
emits ``inspection.state_changed``. A transition taken through this module's route has already done
both, so the subscriber finds the state equal and does nothing; a replayed event does nothing too.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.events import register_event
from aip.platform.events.subscribers import DomainEvent, subscriber

__all__ = [
    "INSPECTION_ANSWER_FAILED",
    "INSPECTION_CREATED",
    "INSPECTION_STATE_CHANGED",
    "ITP_STEP_HOLD_CHANGED",
    "ITP_STEP_RELEASED",
    "WORKFLOW_TRANSITIONED",
    "InspectionAnswerFailedEvent",
    "InspectionCreatedEvent",
    "InspectionStateChangedEvent",
    "ItpStepHoldChangedEvent",
    "ItpStepReleasedEvent",
    "follow_workflow",
]

INSPECTION_ANSWER_FAILED: Final = "inspection.answer_failed"
INSPECTION_CREATED: Final = "inspection.created"
INSPECTION_STATE_CHANGED: Final = "inspection.state_changed"
ITP_STEP_HOLD_CHANGED: Final = "itp_step.hold_changed"
ITP_STEP_RELEASED: Final = "itp_step.released"
WORKFLOW_TRANSITIONED: Final = "workflow.transitioned"

_CONFIG = ConfigDict(
    alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
)


class InspectionCreatedEvent(BaseModel):
    model_config = _CONFIG

    inspection_id: UUID
    asset_id: UUID
    project_id: UUID | None
    kind: str
    template_revision_id: UUID
    source: str


class InspectionStateChangedEvent(BaseModel):
    model_config = _CONFIG

    inspection_id: UUID
    asset_id: UUID
    project_id: UUID | None
    from_state: str = Field(alias="from")
    to_state: str = Field(alias="to")
    action: str


class InspectionAnswerFailedEvent(BaseModel):
    model_config = _CONFIG

    inspection_id: UUID
    response_id: UUID
    field_key: str
    asset_id: UUID
    project_id: UUID | None


class ItpStepReleasedEvent(BaseModel):
    model_config = _CONFIG

    step_id: UUID
    inspection_id: UUID
    asset_id: UUID
    project_id: UUID | None
    point_type: str
    decision: str
    task_id: UUID | None
    blocks_task_id: UUID | None
    released_at: datetime


class ItpStepHoldChangedEvent(BaseModel):
    model_config = _CONFIG

    step_id: UUID
    inspection_id: UUID
    issue_id: UUID
    held: bool


register_event(INSPECTION_ANSWER_FAILED, 1, InspectionAnswerFailedEvent, "inspections")
register_event(INSPECTION_CREATED, 1, InspectionCreatedEvent, "inspections")
register_event(INSPECTION_STATE_CHANGED, 1, InspectionStateChangedEvent, "inspections")
register_event(ITP_STEP_HOLD_CHANGED, 1, ItpStepHoldChangedEvent, "inspections")
register_event(ITP_STEP_RELEASED, 1, ItpStepReleasedEvent, "inspections")


@subscriber(WORKFLOW_TRANSITIONED, 1)
async def follow_workflow(conn: AsyncConnection, event: DomainEvent) -> None:
    if event.payload.get("recordType") != "inspection":
        return
    # Imported here: the service imports this module's event names.
    from aip.modules.inspections.service import sync_state

    await sync_state(conn, UUID(str(event.payload["recordId"])), str(event.payload["action"]))
