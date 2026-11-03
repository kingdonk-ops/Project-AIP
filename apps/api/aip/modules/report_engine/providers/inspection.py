"""The ``inspection`` report data provider (REPORTS-03).

Reads the inspection, its asset (with the ancestors' names for the location line), its project,
the pinned form revision (also when superseded) and the current answers through the owning
modules' published interfaces, on the caller's connection, so another tenant's inspection is
``RecordNotFound``. Viewing it needs ``inspection.view`` on its project.

``record`` is::

    {inspection: {id, kind, state, createdAt},
     asset: {tagNumber, name, internalTag, location: [names root first]},
     project: {code, name, timezone} | null,
     form: {code, revisionNo, schemaHash, sections: [{key, label, fields: [...]}]},
     summary: {answered, failed, missingRequired},
     approval: {approvedAt, approvedBy} | {}}

Each field is ``{key, type, label, unit, required, failed, answer, respondedBy, respondedAt}``,
only for fields (and sections) the current evaluation shows, in schema order. Labels with a
``labelKey`` are resolved to display text here, so the snapshot freezes them. ``answer`` by type:
``measurement`` → ``{valueSi, unit}`` (``unit`` is the SI unit ``fmt_measure`` takes; an unknown
unit keeps ``{value, unit, valueSi: null}``), ``dropdown``/``multi_select`` → option labels,
``photo``/``signature`` → file entries, anything else the stored value. ``respondedBy`` is a
display name (``identity.api.get_display_names``), ``respondedAt`` UTC.

Photos and signatures: a JPEG, PNG or WebP of at most 3 MB is embedded (``ReportSource.files``
with role ``photo:<fieldKey>`` / ``signature:<fieldKey>``, entry ``{fileId, asset}`` with the
render job's asset name), at most 40 per report in schema order. Anything else is ``{fileId,
omitted}`` with ``not_an_image``, ``too_large``, ``too_many`` or ``unavailable`` (the file is gone
or not clean), shown with ``report.inspection.photo_omitted.<reason>``.

``context`` (the auto-render trigger) gives ``approvedAt`` (the event's time) and ``approvedBy``
(its actor, shown as a display name); a manual render has an empty ``approval``. The register label
is ``"<project code> <tag> <asset name>"``. Every read goes through ``InspectionDeps``, so the unit
tests run the provider on fakes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.assets.api import AssetOut, AssetsApi
from aip.modules.forms.api import FormRevisionOut, FormsApi
from aip.modules.identity.api import get_display_names
from aip.modules.inspections.api import CurrentResponses, InspectionOut, InspectionsApi
from aip.modules.projects.api import ProjectOut, ProjectsApi
from aip.modules.report_engine.jobs import asset_name
from aip.modules.report_engine.providers import (
    RecordNotFound,
    ReportSource,
    SourceFile,
    register_provider,
)
from aip.modules.report_engine.snapshots import DEFAULT_LOCALE
from aip.modules.terms.api import UnknownUnitError, bulk_resolve, si_unit, to_si
from aip.modules.uploads.api import StoredFileRef, get_stored_file
from aip.platform.context import get_context

__all__ = [
    "IMAGE_MAX_BYTES",
    "IMAGE_TYPES",
    "INSPECTION_RECORD_TYPE",
    "MAX_IMAGES",
    "InspectionDeps",
    "InspectionProvider",
    "default_deps",
    "install",
]

INSPECTION_RECORD_TYPE: Final = "inspection"
IMAGE_TYPES: Final = frozenset({"image/jpeg", "image/png", "image/webp"})
IMAGE_MAX_BYTES: Final = 3 * 1024 * 1024
MAX_IMAGES: Final = 40
_FILE_TYPES: Final = frozenset({"photo", "signature"})


@dataclass(frozen=True, slots=True)
class InspectionDeps:
    """The published-interface reads the provider makes (fakes in the unit tests)."""

    get_inspection: Callable[[AsyncConnection, UUID], Awaitable[InspectionOut | None]]
    get_current_responses: Callable[[AsyncConnection, UUID], Awaitable[CurrentResponses | None]]
    get_asset: Callable[[AsyncConnection, UUID], Awaitable[AssetOut | None]]
    get_ancestor_names: Callable[[AsyncConnection, UUID], Awaitable[list[str]]]
    get_project: Callable[[AsyncConnection, UUID], Awaitable[ProjectOut | None]]
    get_revision: Callable[[AsyncConnection, UUID], Awaitable[FormRevisionOut | None]]
    get_display_names: Callable[[AsyncConnection, Iterable[UUID]], Awaitable[dict[UUID, str]]]
    get_stored_file: Callable[[AsyncConnection, UUID], Awaitable[StoredFileRef | None]]
    resolve_labels: Callable[[AsyncConnection, list[str], UUID | None], Awaitable[dict[str, str]]]


async def _resolve_labels(
    conn: AsyncConnection, keys: list[str], project_id: UUID | None
) -> dict[str, str]:
    if not keys:
        return {}
    tenant_id = get_context().tenant_id
    return await bulk_resolve(
        conn, keys, DEFAULT_LOCALE, tenant_id=tenant_id, project_id=project_id
    )


def default_deps() -> InspectionDeps:
    inspections, assets, projects, forms = InspectionsApi(), AssetsApi(), ProjectsApi(), FormsApi()
    return InspectionDeps(
        get_inspection=inspections.get_inspection,
        get_current_responses=inspections.get_current_responses,
        get_asset=assets.get_asset,
        get_ancestor_names=assets.get_ancestor_names,
        get_project=projects.get_project,
        get_revision=forms.get_revision,
        get_display_names=get_display_names,
        get_stored_file=get_stored_file,
        resolve_labels=_resolve_labels,
    )


def _utc_z(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _as_uuid(value: Any) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _as_instant(value: Any) -> str | None:
    if isinstance(value, datetime):
        return _utc_z(value)
    return None if value is None else str(value)


def _label_keys(sections: Sequence[Mapping[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for section in sections:
        if section.get("labelKey"):
            keys.add(str(section["labelKey"]))
        for spec in section.get("fields", []):
            if spec.get("labelKey"):
                keys.add(str(spec["labelKey"]))
            for option in spec.get("options", []):
                if option.get("labelKey"):
                    keys.add(str(option["labelKey"]))
    return sorted(keys)


def _text(spec: Mapping[str, Any], labels: Mapping[str, str]) -> str:
    """The resolved ``labelKey`` text, else the form's own ``label``."""
    key = spec.get("labelKey")
    if key and key in labels:
        return labels[key]
    return str(spec.get("label", ""))


class _Files:
    """Decides which referenced files are embedded, in schema order, within the report's budget."""

    def __init__(self, conn: AsyncConnection, deps: InspectionDeps) -> None:
        self._conn = conn
        self._deps = deps
        self.embedded: list[SourceFile] = []

    async def entry(self, field_type: str, field_key: str, value: Any) -> dict[str, Any]:
        file_id = _as_uuid(value.get("fileId")) if isinstance(value, Mapping) else None
        if file_id is None:
            return {"fileId": None, "omitted": "unavailable"}
        ref = await self._deps.get_stored_file(self._conn, file_id)
        reason: str | None = None
        if ref is None:
            reason = "unavailable"
        elif ref.content_type not in IMAGE_TYPES:
            reason = "not_an_image"
        elif ref.size_bytes > IMAGE_MAX_BYTES:
            reason = "too_large"
        elif len(self.embedded) >= MAX_IMAGES:
            reason = "too_many"
        if reason is not None or ref is None:
            return {"fileId": str(file_id), "omitted": reason}
        self.embedded.append(SourceFile(file_id=file_id, role=f"{field_type}:{field_key}"))
        return {"fileId": str(file_id), "asset": asset_name(str(file_id), ref.content_type)}


async def _answer(
    spec: Mapping[str, Any], value: Any, labels: Mapping[str, str], files: _Files
) -> Any:
    ftype, key = str(spec["type"]), str(spec["key"])
    if ftype == "measurement" and isinstance(value, Mapping):
        unit = str(value.get("unit", spec.get("unit", "")))
        try:
            return {"valueSi": to_si(float(value["value"]), unit), "unit": si_unit(unit)}
        except (UnknownUnitError, KeyError, TypeError, ValueError):
            return {"value": value.get("value"), "unit": unit, "valueSi": None}
    if ftype in ("dropdown", "multi_select"):
        options = {str(o["value"]): _text(o, labels) for o in spec.get("options", [])}
        if isinstance(value, list):
            return [options.get(str(v), str(v)) for v in value]
        return options.get(str(value), str(value))
    if ftype == "photo":
        items = value if isinstance(value, list) else []
        return [await files.entry(ftype, key, item) for item in items]
    if ftype == "signature":
        return await files.entry(ftype, key, value)
    return value


class InspectionProvider:
    """``provide(conn, inspection_id, *, context)`` for record type ``inspection``."""

    def __init__(self, deps: InspectionDeps | None = None) -> None:
        self._deps = deps

    @property
    def deps(self) -> InspectionDeps:
        if self._deps is None:
            self._deps = default_deps()
        return self._deps

    async def __call__(
        self, conn: AsyncConnection, record_id: UUID, *, context: Mapping[str, Any]
    ) -> ReportSource:
        d = self.deps
        inspection = await d.get_inspection(conn, record_id)
        if inspection is None:
            raise RecordNotFound(f"inspection {record_id}")
        asset = await d.get_asset(conn, inspection.asset_id)
        if asset is None:
            raise RecordNotFound(f"asset {inspection.asset_id}")
        project = None
        if inspection.project_id is not None:
            project = await d.get_project(conn, inspection.project_id)
            if project is None:
                raise RecordNotFound(f"project {inspection.project_id}")
        revision = await d.get_revision(conn, inspection.template_revision_id)
        responses = await d.get_current_responses(conn, record_id)
        if revision is None or responses is None:
            raise RecordNotFound(f"inspection {record_id} form")

        schema_sections: list[Mapping[str, Any]] = list(revision.schema.get("sections", []))
        labels = await d.resolve_labels(conn, _label_keys(schema_sections), inspection.project_id)
        approved_by = _as_uuid(context.get("approvedBy"))
        users = {a.responded_by for a in responses.answers.values()}
        names = await d.get_display_names(
            conn, sorted(users | ({approved_by} if approved_by else set()), key=str)
        )

        visible = responses.evaluation.visible
        failed = set(responses.evaluation.failed)
        required = responses.evaluation.required
        files = _Files(conn, d)
        sections: list[dict[str, Any]] = []
        answered = failed_count = 0
        for section in schema_sections:
            if not visible.get(str(section["key"]), True):
                continue
            fields: list[dict[str, Any]] = []
            for spec in section.get("fields", []):
                key = str(spec["key"])
                if not visible.get(key, True):
                    continue
                current = responses.answers.get(key)
                is_failed = key in failed
                answered += current is not None
                failed_count += is_failed
                fields.append(
                    {
                        "key": key,
                        "type": str(spec["type"]),
                        "label": _text(spec, labels),
                        "unit": spec.get("unit"),
                        "required": bool(required.get(key, spec.get("required", False))),
                        "failed": is_failed,
                        "answer": None
                        if current is None
                        else await _answer(spec, current.value, labels, files),
                        "respondedBy": None if current is None else names.get(current.responded_by),
                        "respondedAt": None if current is None else _utc_z(current.responded_at),
                    }
                )
            if fields:
                sections.append(
                    {"key": str(section["key"]), "label": _text(section, labels), "fields": fields}
                )

        approval: dict[str, Any] = {}
        if context:
            approval = {
                "approvedAt": _as_instant(context.get("approvedAt")),
                "approvedBy": None if approved_by is None else names.get(approved_by),
            }
        tag = asset.tag_number or asset.internal_tag
        label = " ".join(p for p in (project.code if project else None, tag, asset.name) if p)
        return ReportSource(
            project_id=inspection.project_id,
            record_version=inspection.sync_version,
            data={
                "inspection": {
                    "id": str(inspection.id),
                    "kind": inspection.kind,
                    "state": inspection.state,
                    "createdAt": _utc_z(inspection.created_at),
                },
                "asset": {
                    "tagNumber": asset.tag_number,
                    "name": asset.name,
                    "internalTag": asset.internal_tag,
                    "location": await d.get_ancestor_names(conn, asset.id),
                },
                "project": None
                if project is None
                else {"code": project.code, "name": project.name, "timezone": project.timezone},
                "form": {
                    "code": revision.template_code,
                    "revisionNo": revision.revision_no,
                    "schemaHash": revision.schema_hash,
                    "sections": sections,
                },
                "summary": {
                    "answered": answered,
                    "failed": failed_count,
                    "missingRequired": len(responses.evaluation.missing_required),
                },
                "approval": approval,
            },
            files=tuple(files.embedded),
            time_zone_hint=None if project is None else project.timezone,
            label=label,
        )


inspection_source = InspectionProvider()


def install() -> None:
    """Register the provider (idempotent)."""
    register_provider(INSPECTION_RECORD_TYPE, inspection_source, view_permission="inspection.view")
