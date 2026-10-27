"""Domain events forms publishes (via the outbox, ADR 0003).

- ``form.revision_published`` v1: a revision became the template's current published revision
  (FORMS-01). Payload ``{templateId, revisionId, revisionNo, code, kind, schemaHash}``. Inspections
  (and the report engine) listen so a pinned form is known the moment it is published.

The model is registered with the platform's event schemas when this module loads.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = ["FORM_REVISION_PUBLISHED", "RevisionPublished"]

FORM_REVISION_PUBLISHED: Final = "form.revision_published"


class _Event(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class RevisionPublished(_Event):
    template_id: UUID
    revision_id: UUID
    revision_no: int
    code: str
    kind: str
    schema_hash: str


register_event(FORM_REVISION_PUBLISHED, 1, RevisionPublished, "forms")
