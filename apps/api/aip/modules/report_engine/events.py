"""Domain events report_engine publishes (via the outbox, ADR 0003).

- ``report.template_published`` v1: a report template version became published, by an API publish
  or by the config loader (REPORTS-01). Payload ``{templateId, key, variant, version, recordType}``.

The model is registered with the platform's event schemas when this module loads.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = ["REPORT_TEMPLATE_PUBLISHED", "TemplatePublished"]

REPORT_TEMPLATE_PUBLISHED: Final = "report.template_published"


class TemplatePublished(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    template_id: UUID
    key: str
    variant: str
    version: int
    record_type: str


register_event(REPORT_TEMPLATE_PUBLISHED, 1, TemplatePublished, "report_engine")
