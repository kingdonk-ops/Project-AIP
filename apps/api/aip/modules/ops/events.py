"""Domain events the ops module publishes (via the outbox, ADR 0003).

``job.completed`` and ``job.failed`` v1 (OPS-03): written by the job runner in the same transaction
as the job's final status, for notifications to tell the requester. Payload: ``{jobId, jobType,
status, requestedBy, correlationId, resultRef, error}``.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from aip.platform.events import register_event

__all__ = ["JOB_COMPLETED", "JOB_FAILED", "JobFinished"]

JOB_COMPLETED = "job.completed"
JOB_FAILED = "job.failed"


class JobFinished(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    job_id: UUID
    job_type: str
    status: str
    requested_by: UUID | None = None
    correlation_id: UUID
    result_ref: str | None = None
    error: str | None = None


for _name in (JOB_COMPLETED, JOB_FAILED):
    register_event(_name, 1, JobFinished, "ops")
