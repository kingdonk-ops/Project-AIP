"""Pydantic request/response models for forms (FORMS-01).

JSON is camelCase (``changeNote``, ``schemaHash``), bodies forbid unknown fields. The revision
``schema`` is carried on a ``schema_`` attribute aliased to ``schema`` on the wire, because a
Pydantic field literally named ``schema`` shadows ``BaseModel.schema``. ``FormRevisionOut`` (the
cross-module DTO in ``api``) is a plain dataclass so consumers read ``.schema`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    "FormErrorBody",
    "FormRevisionOut",
    "LintBody",
    "LintIssueOut",
    "LintResult",
    "PublishBody",
    "RevisionCreate",
    "RevisionOut",
    "RevisionReplace",
    "RevisionSummary",
    "TemplateCreate",
    "TemplateDetail",
    "TemplateListItem",
    "TemplatePage",
    "TemplateRecord",
    "UploadResult",
]

Kind = Literal["inspection", "itp", "rfi", "permit", "test_report"]
TemplateStatus = Literal["draft", "active", "retired"]
RevisionStatus = Literal["draft", "published", "superseded"]

# A template code is a slug (2-63 chars); the same pattern as the ck_form_templates_code CHECK.
Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,62}$")]
Name = Annotated[str, Field(min_length=1, max_length=200)]
ChangeNote = Annotated[str, Field(max_length=2000)]
SchemaObject = dict[str, Any]


class _In(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response built from database rows: columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class FormErrorBody(_Out):
    """A domain error: a stable ``code`` (``CODE_TAKEN``, ``TEMPLATE_INVALID``, ...) plus extras
    such as the lint ``issues`` or a ``VERSION_CONFLICT`` ``current`` row."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")

    code: str


# --- request bodies ---------------------------------------------------------------------------


class TemplateCreate(_In):
    code: Code
    name: Name
    kind: Kind
    schema_: SchemaObject = Field(alias="schema")
    change_note: ChangeNote | None = None


class RevisionCreate(_In):
    """A new draft revision. ``schema`` omitted copies the current published schema."""

    schema_: SchemaObject | None = Field(default=None, alias="schema")
    change_note: ChangeNote | None = None


class RevisionReplace(_In):
    schema_: SchemaObject = Field(alias="schema")
    change_note: ChangeNote | None = None


class PublishBody(_In):
    expected_sync_version: int | None = Field(default=None, ge=1)


class LintBody(_In):
    schema_: SchemaObject = Field(alias="schema")


# --- lint -------------------------------------------------------------------------------------


class LintIssueOut(_Out):
    path: list[str | int]
    code: str
    message: str


class LintResult(_Out):
    issues: list[LintIssueOut]


# --- responses --------------------------------------------------------------------------------


class RevisionSummary(_Out):
    id: UUID
    revision_no: int
    status: RevisionStatus
    schema_hash: str | None
    change_note: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RevisionOut(_Out):
    id: UUID
    template_id: UUID
    revision_no: int
    status: RevisionStatus
    schema_: SchemaObject = Field(alias="schema")
    schema_hash: str | None
    evaluator_version: str | None
    change_note: str | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TemplateRecord(_Out):
    id: UUID
    code: str
    name: str
    kind: Kind
    status: TemplateStatus
    current_revision_id: UUID | None
    current_revision_no: int | None
    sync_version: int
    created_at: datetime
    updated_at: datetime


class TemplateListItem(_Out):
    id: UUID
    code: str
    name: str
    kind: Kind
    status: TemplateStatus
    current_revision_no: int | None
    updated_at: datetime


class TemplatePage(_Out):
    items: list[TemplateListItem]


class TemplateDetail(TemplateRecord):
    revisions: list[RevisionSummary]


class UploadResult(_Out):
    template: TemplateRecord
    revision: RevisionOut


@dataclass(frozen=True, slots=True)
class FormRevisionOut:
    """A frozen (or draft) revision as the forms published interface returns it to other modules.

    ``schema`` is the revision's full JSON. A draft carries ``schema_hash``/``published_at`` as
    ``None``; ``api.get_revision`` never returns a draft.
    """

    id: UUID
    template_id: UUID
    template_code: str
    kind: str
    revision_no: int
    status: str
    schema: dict[str, Any]
    schema_hash: str | None
    evaluator_version: str | None
    published_at: datetime | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> FormRevisionOut:
        return cls(
            id=row["id"],
            template_id=row["template_id"],
            template_code=row["template_code"],
            kind=row["kind"],
            revision_no=row["revision_no"],
            status=row["status"],
            schema=row["schema"],
            schema_hash=row["schema_hash"],
            evaluator_version=row["evaluator_version"],
            published_at=row["published_at"],
        )
