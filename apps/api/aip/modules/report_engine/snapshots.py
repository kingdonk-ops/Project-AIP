"""Report data snapshots (REPORTS-02): the frozen, hashed input of one render.

``build_snapshot`` freezes everything a render reads besides the template: the record data from
the provider, the resolved labels of the template's ``termKeys`` (for the tenant and the record's
project), the locale, the IANA time zone (the project's, else ``UTC``, ADR 0025), the display unit
system and the pinned stored files with their sha256. The body is::

    {schemaVersion: 1, recordType, recordId, recordVersion, record, labels, locale, timeZone,
     unitSystem, files}

``data_hash`` is the sha256 (hex) of the body's RFC 8785 canonical JSON. No clock value goes into
the body, so the same data gives the same hash, and the row is inserted ``ON CONFLICT DO NOTHING``
on ``(tenant_id, record_type, record_id, data_hash)`` then read back: a repeat reuses the existing
snapshot. A canonical body over 5 MB is refused with 422 ``SNAPSHOT_TOO_LARGE``.

``report_data_snapshots`` is append-only: no runtime role may change or delete a row.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast
from uuid import UUID

import rfc8785
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine import repository as repo
from aip.modules.report_engine.providers import RecordNotFound, ReportSource
from aip.modules.report_engine.schemas import TemplateRow
from aip.modules.terms.api import UnitSystem, bulk_resolve, display_system
from aip.modules.uploads.api import get_stored_file
from aip.platform.context import get_context, new_request_id
from aip.platform.http import DomainError

__all__ = [
    "DEFAULT_LOCALE",
    "DEFAULT_TIME_ZONE",
    "SNAPSHOT_MAX_BYTES",
    "SNAPSHOT_SCHEMA_VERSION",
    "Snapshot",
    "build_snapshot",
    "hash_body",
    "snapshot_body",
]

SNAPSHOT_SCHEMA_VERSION: Final = 1
SNAPSHOT_MAX_BYTES: Final = 5 * 1024 * 1024
DEFAULT_LOCALE: Final = "en-AU"
DEFAULT_TIME_ZONE: Final = "UTC"


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One ``report_data_snapshots`` row; ``data`` is the snapshot body."""

    id: UUID
    record_type: str
    record_id: UUID
    record_version: int | None
    project_id: UUID | None
    data: Mapping[str, Any]
    data_hash: str
    size_bytes: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Snapshot:
        return cls(
            id=row["id"],
            record_type=row["record_type"],
            record_id=row["record_id"],
            record_version=row["record_version"],
            project_id=row["project_id"],
            data=row["data"],
            data_hash=row["data_hash"],
            size_bytes=int(row["size_bytes"]),
            created_at=row["created_at"],
        )

    @property
    def record(self) -> dict[str, Any]:
        return dict(self.data.get("record", {}))

    @property
    def labels(self) -> dict[str, str]:
        return dict(self.data.get("labels", {}))

    @property
    def locale(self) -> str:
        return str(self.data.get("locale", DEFAULT_LOCALE))

    @property
    def time_zone(self) -> str:
        return str(self.data.get("timeZone", DEFAULT_TIME_ZONE))

    @property
    def unit_system(self) -> UnitSystem:
        return cast(UnitSystem, self.data.get("unitSystem", "metric"))

    @property
    def files(self) -> list[dict[str, Any]]:
        return [dict(f) for f in self.data.get("files", [])]


def snapshot_body(
    *,
    record_type: str,
    record_id: UUID,
    record_version: int | None,
    record: Mapping[str, Any],
    labels: Mapping[str, str],
    locale: str,
    time_zone: str,
    unit_system: str,
    files: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The snapshot body (plain JSON; no clock value)."""
    return {
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
        "recordType": record_type,
        "recordId": str(record_id),
        "recordVersion": record_version,
        "record": dict(record),
        "labels": dict(labels),
        "locale": locale,
        "timeZone": time_zone,
        "unitSystem": unit_system,
        "files": [dict(f) for f in files],
    }


def hash_body(body: Mapping[str, Any]) -> tuple[str, int]:
    """``(sha256 hex, size)`` of ``body``'s RFC 8785 JSON; 422 ``SNAPSHOT_TOO_LARGE`` over 5 MB."""
    canonical = rfc8785.dumps(dict(body))
    if len(canonical) > SNAPSHOT_MAX_BYTES:
        raise DomainError(422, "SNAPSHOT_TOO_LARGE", detail="the report data exceeds 5 MB")
    return hashlib.sha256(canonical).hexdigest(), len(canonical)


async def _pinned_files(conn: AsyncConnection, source: ReportSource) -> list[dict[str, Any]]:
    pinned: list[dict[str, Any]] = []
    for entry in source.files:
        ref = await get_stored_file(conn, entry.file_id)
        if ref is None:  # missing, another tenant's, out of scope or not clean
            raise RecordNotFound(f"file {entry.file_id}")
        pinned.append(
            {
                "fileId": str(ref.id),
                "role": entry.role,
                "sha256": ref.sha256,
                "sizeBytes": ref.size_bytes,
                "contentType": ref.content_type,
            }
        )
    return pinned


async def build_snapshot(
    conn: AsyncConnection,
    template: TemplateRow,
    source: ReportSource,
    *,
    record_id: UUID,
    created_by: UUID | None = None,
    locale: str = DEFAULT_LOCALE,
) -> Snapshot:
    """Freeze ``source`` for ``template`` and store it (or reuse the identical snapshot)."""
    tenant_id = get_context().tenant_id
    keys = sorted(str(k) for k in template.definition.get("termKeys", []))
    labels = await bulk_resolve(
        conn, keys, locale, tenant_id=tenant_id, project_id=source.project_id
    )
    body = snapshot_body(
        record_type=template.record_type,
        record_id=record_id,
        record_version=source.record_version,
        record=source.data,
        labels=labels,
        locale=locale,
        time_zone=source.time_zone_hint or DEFAULT_TIME_ZONE,
        unit_system=await display_system(conn, tenant_id, source.project_id),
        files=await _pinned_files(conn, source),
    )
    data_hash, size = hash_body(body)
    row = await repo.insert_snapshot(
        conn,
        {
            "id": UUID(new_request_id()),
            "tenant_id": tenant_id,
            "record_type": template.record_type,
            "record_id": record_id,
            "record_version": source.record_version,
            "project_id": source.project_id,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "data": body,
            "data_hash": data_hash,
            "size_bytes": size,
            "created_by": created_by,
        },
    )
    return Snapshot.from_row(row)
