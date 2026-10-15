"""Pydantic models for the security tables (SECURITY-02).

JSON is camelCase. Each ``Literal`` mirrors the CHECK constraint of the same column in
``202610151900_security_tables``, so a value the database would refuse is a 422 first. The
services and routes that use these arrive with SECURITY-03 to SECURITY-06.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    "AccessReviewStatus",
    "BreachStatus",
    "ControlRecord",
    "ControlRecordCreate",
    "ControlStatus",
    "DataClassification",
    "EvidenceType",
    "RestoreResult",
]

ControlStatus = Literal["specified", "implemented", "proven"]
EvidenceType = Literal["ci_artefact", "screenshot", "report", "sign_off"]
AccessReviewStatus = Literal["open", "in_review", "signed_off"]
RestoreResult = Literal["pass", "fail"]
DataClassification = Literal["public", "internal", "sensitive", "health"]
BreachStatus = Literal["open", "assessing", "notified", "closed"]

ControlKey = Annotated[str, Field(min_length=1, max_length=64)]
Title = Annotated[str, Field(min_length=1, max_length=255)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="ignore"
    )


class ControlRecordCreate(_Model):
    control_key: ControlKey
    title: Title
    framework_mappings: dict[str, Any] = Field(default_factory=dict[str, Any])
    owner_user_id: UUID | None = None
    status: ControlStatus = "specified"
    evidence_source: str | None = Field(default=None, max_length=255)


class ControlRecord(_Out):
    id: UUID
    control_key: str
    title: str
    framework_mappings: dict[str, Any]
    owner_user_id: UUID | None
    status: ControlStatus
    evidence_source: str | None
    created_at: datetime
    updated_at: datetime
