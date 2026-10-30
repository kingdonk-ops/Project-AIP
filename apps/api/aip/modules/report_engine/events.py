"""Domain events report_engine publishes (via the outbox, ADR 0003).

- ``report.template_published`` v1: a report template version became published, by an API publish
  or by the config loader (REPORTS-01). Payload ``{templateId, key, variant, version, recordType}``.
- ``report.render_succeeded`` v1 (REPORTS-02): a render job stored its PDF. Payload
  ``{renderJobId, templateKey, templateVersion, variant, recordType, recordId, dataHash, fileId,
  pdfSha256}``.
- ``report.render_failed`` v1 (REPORTS-02): a render job ended ``failed``. Payload
  ``{renderJobId, templateKey, variant, recordType, recordId, errorCode}``.

The models are registered with the platform's event schemas when this module loads.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = [
    "REPORT_RENDER_FAILED",
    "REPORT_RENDER_SUCCEEDED",
    "REPORT_TEMPLATE_PUBLISHED",
    "RenderFailed",
    "RenderSucceeded",
    "TemplatePublished",
]

REPORT_TEMPLATE_PUBLISHED: Final = "report.template_published"
REPORT_RENDER_SUCCEEDED: Final = "report.render_succeeded"
REPORT_RENDER_FAILED: Final = "report.render_failed"


class _Payload(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class TemplatePublished(_Payload):
    template_id: UUID
    key: str
    variant: str
    version: int
    record_type: str


class RenderSucceeded(_Payload):
    render_job_id: UUID
    template_key: str
    template_version: int
    variant: str
    record_type: str
    record_id: UUID
    data_hash: str
    file_id: UUID
    pdf_sha256: str


class RenderFailed(_Payload):
    render_job_id: UUID
    template_key: str
    variant: str
    record_type: str
    record_id: UUID
    error_code: str


register_event(REPORT_TEMPLATE_PUBLISHED, 1, TemplatePublished, "report_engine")
register_event(REPORT_RENDER_SUCCEEDED, 1, RenderSucceeded, "report_engine")
register_event(REPORT_RENDER_FAILED, 1, RenderFailed, "report_engine")
