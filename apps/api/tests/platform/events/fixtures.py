"""The fixture event for the outbox tests: ``widget.created`` v1."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from aip.platform.events import DictEventSchemaLookup


class WidgetCreated(BaseModel):
    widget_id: UUID
    name: str


SCHEMAS = DictEventSchemaLookup({("widget.created", 1): WidgetCreated})
