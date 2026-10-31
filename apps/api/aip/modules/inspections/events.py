"""Domain events the inspections module publishes and consumes (via the outbox, ADR 0003).

- ``inspection.created`` v1 ``{inspectionId, assetId, projectId, kind, templateRevisionId,
  source}``: emitted in the create's transaction.
- ``inspection.state_changed`` v1 ``{inspectionId, assetId, projectId, from, to, action}``: an
  applied transition moved the inspection's lifecycle. Emitted in the transition's transaction when
  it went through ``/api/v1/inspections``, else by :func:`follow_workflow` below.

``follow_workflow`` subscribes to approvals' ``workflow.transitioned`` v1: for an ``inspection``
record whose cached ``state`` differs from its instance's ``current_state`` it updates the cache and
emits ``inspection.state_changed``. A transition taken through this module's route has already done
both, so the subscriber finds the state equal and does nothing; a replayed event does nothing too.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.events import register_event
from aip.platform.events.subscribers import DomainEvent, subscriber

__all__ = [
    "INSPECTION_CREATED",
    "INSPECTION_STATE_CHANGED",
    "WORKFLOW_TRANSITIONED",
    "InspectionCreatedEvent",
    "InspectionStateChangedEvent",
    "follow_workflow",
]

INSPECTION_CREATED: Final = "inspection.created"
INSPECTION_STATE_CHANGED: Final = "inspection.state_changed"
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


register_event(INSPECTION_CREATED, 1, InspectionCreatedEvent, "inspections")
register_event(INSPECTION_STATE_CHANGED, 1, InspectionStateChangedEvent, "inspections")


@subscriber(WORKFLOW_TRANSITIONED, 1)
async def follow_workflow(conn: AsyncConnection, event: DomainEvent) -> None:
    if event.payload.get("recordType") != "inspection":
        return
    # Imported here: the service imports this module's event names.
    from aip.modules.inspections.service import sync_state

    await sync_state(conn, UUID(str(event.payload["recordId"])), str(event.payload["action"]))
