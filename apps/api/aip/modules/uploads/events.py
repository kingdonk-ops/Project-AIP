"""Domain events the uploads module publishes on release (UPLOADS-02, ADR 0003).

``upload.completed`` (v1) is emitted in the release transaction when a scanned object is released
into tenant storage; ``upload.rejected`` (v1) is emitted when the pipeline fails a stage or a scan
could not complete on the last attempt. Both carry the session and project so documents and
notifications can react without reaching into the uploads tables. The models register with the
platform event registry on import (ARCH-06 loads this via ``load_module_events``).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = [
    "UPLOAD_COMPLETED",
    "UPLOAD_REJECTED",
    "UploadCompletedEvent",
    "UploadRejectedEvent",
]

UPLOAD_COMPLETED = "upload.completed"
UPLOAD_REJECTED = "upload.rejected"

_CONFIG = ConfigDict(
    alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
)


class UploadCompletedEvent(BaseModel):
    """``upload.completed`` v1: a scanned object was released into tenant storage."""

    model_config = _CONFIG

    session_id: UUID
    file_id: UUID
    project_id: UUID
    detected_mime: str
    size_bytes: int
    sha256: str


class UploadRejectedEvent(BaseModel):
    """``upload.rejected`` v1: the upload was rejected; ``reason`` is the failing stage or code."""

    model_config = _CONFIG

    session_id: UUID
    project_id: UUID
    reason: str


register_event(UPLOAD_COMPLETED, 1, UploadCompletedEvent, "uploads")
register_event(UPLOAD_REJECTED, 1, UploadRejectedEvent, "uploads")
