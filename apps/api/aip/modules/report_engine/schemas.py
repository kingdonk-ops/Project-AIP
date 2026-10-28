"""Pydantic request/response models for report templates (REPORTS-01).

JSON uses camelCase. Request models forbid unknown keys (an unknown key is a 422). The package
inside an upload is validated by ``template_package.parse_package``, not here, so its errors carry
the package codes (``SCHEMA_INVALID``, ``HTML_POLICY``, ...).

``TemplateRow`` is a stored template with its asset bytes: what ``ReportTemplatesApi`` returns and
what ``render_html`` accepts.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

__all__ = [
    "AssetInfo",
    "ReportErrorBody",
    "StoredAsset",
    "ReportTemplateDetail",
    "ReportTemplatePage",
    "TemplateRow",
    "TemplateStatus",
    "ReportTemplateSummary",
    "ReportTemplateUpload",
    "TemplateVariant",
]

TemplateStatus = Literal["draft", "published", "retired"]
TemplateVariant = Literal["internal", "client", "certificate"]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class _Out(BaseModel):
    """A response: built from database rows, so columns the API does not show are ignored."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class ReportErrorBody(_Out):
    """A domain error: a stable ``code``; package errors add ``path`` and ``detail``."""

    code: str
    path: str | None = None
    detail: str | None = None


class ReportTemplateUpload(_Model):
    """A template package as JSON: ``template.json`` as ``definition``, the body, the stylesheet,
    the sample data and ``assets`` mapping each declared asset name to its base64 bytes."""

    definition: dict[str, Any]
    body: str = Field(max_length=512 * 1024)
    css: str = Field(max_length=256 * 1024)
    sample_data: dict[str, Any] = Field(default_factory=dict[str, Any])
    assets: dict[str, str] = Field(default_factory=dict[str, str], max_length=20)


class StoredAsset(_Out):
    """One asset as stored in ``report_templates.assets``."""

    content_type: str
    sha256: str
    size_bytes: int
    data_base64: str


class AssetInfo(_Out):
    name: str
    content_type: str
    size_bytes: int
    sha256: str


class ReportTemplateSummary(_Out):
    id: UUID
    key: str
    version: int
    variant: TemplateVariant
    record_type: str
    name_key: str
    orientation: Literal["portrait", "landscape"]
    paper: Literal["A4", "A3"]
    status: TemplateStatus
    source: Literal["config", "upload"]
    content_sha256: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReportTemplateDetail(ReportTemplateSummary):
    definition: dict[str, Any]
    body: str
    css: str
    assets: list[AssetInfo]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ReportTemplateDetail:
        assets = [
            AssetInfo(
                name=name,
                content_type=stored["contentType"],
                size_bytes=stored["sizeBytes"],
                sha256=stored["sha256"],
            )
            for name, stored in sorted(row["assets"].items())
        ]
        return cls.model_validate({**row, "assets": assets})


class ReportTemplatePage(_Out):
    items: list[ReportTemplateSummary]
    next_cursor: str | None


class TemplateRow(_Out):
    """A stored template with its assets, for the render contract (``render_html``).

    ``definition`` is ``template.json`` as uploaded plus its ``sampleData``.
    """

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore", frozen=True
    )

    id: UUID
    key: str
    version: int
    variant: TemplateVariant
    record_type: str
    name_key: str
    orientation: Literal["portrait", "landscape"]
    paper: Literal["A4", "A3"]
    definition: dict[str, Any]
    body: str
    css: str
    assets: dict[str, StoredAsset]
    content_sha256: str
    status: TemplateStatus
    source: Literal["config", "upload"]
    client_company_id: UUID | None
    published_at: datetime | None

    @property
    def sample_data(self) -> dict[str, Any]:
        return dict(self.definition.get("sampleData", {}))

    def asset_files(self) -> dict[str, tuple[str, bytes]]:
        """``{name: (contentType, bytes)}`` for the render contract."""
        return {
            name: (asset.content_type, base64.b64decode(asset.data_base64))
            for name, asset in self.assets.items()
        }
