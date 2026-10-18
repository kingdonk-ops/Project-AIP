"""Domain events approvals publishes (via the outbox, ADR 0003).

- ``workflow.transitioned`` v1: a transition took effect (APPROVALS-02). Payload
  ``{instanceId, recordType, recordId, projectId, from, to, action, actorId, definitionKey,
  definitionVersion}``. A decision left ``pending_countersign`` emits nothing; the countersign that
  applies it emits this event.
- ``workflow.definition_published`` v1: a draft became the active version
  ``{definitionId, key, version, recordType, projectId, previousDefinitionId}``.

The models are registered with the platform's event schemas when this module loads.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = [
    "WORKFLOW_DEFINITION_PUBLISHED",
    "WORKFLOW_TRANSITIONED",
    "DefinitionPublished",
    "WorkflowTransitioned",
]

WORKFLOW_TRANSITIONED: Final = "workflow.transitioned"
WORKFLOW_DEFINITION_PUBLISHED: Final = "workflow.definition_published"


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


register_event(WORKFLOW_TRANSITIONED, 1, WorkflowTransitioned, "approvals")
register_event(WORKFLOW_DEFINITION_PUBLISHED, 1, DefinitionPublished, "approvals")
