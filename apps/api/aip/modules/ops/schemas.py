"""Pydantic models for the ops job records (OPS-01)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobStatus(StrEnum):
    """Stable internal job status codes (labels come from terminology keys, never these)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_STATUSES


TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
)


class JobView(BaseModel):
    """A user-visible job record (one ``jobs`` row)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: UUID
    tenant_id: UUID
    job_type: str
    status: JobStatus
    idempotency_key: str | None
    correlation_id: UUID
    attempts: int
    payload: dict[str, Any]
    result_ref: str | None
    error: str | None
    requested_by: UUID | None
    procrastinate_job_id: int | None
    created_at: datetime
    updated_at: datetime


class JobEventView(BaseModel):
    """One state change of a job (one ``job_events`` row)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: UUID
    tenant_id: UUID
    job_id: UUID
    seq: int
    from_status: JobStatus | None
    to_status: JobStatus
    detail: dict[str, Any]
    occurred_at: datetime
