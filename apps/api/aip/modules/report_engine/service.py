"""Business logic for report templates (REPORTS-01).

``TemplateService`` runs on the caller's ``with_tenant`` connection (the routes open one per
request; the loader one per tenant) under the matching request context, so RLS keeps each tenant
to its own rows and another tenant's id reads as 404 ``TEMPLATE_NOT_FOUND``.

- ``create_draft`` takes the next version of ``(key, variant)`` under ``FOR UPDATE`` of the existing
  rows (soft-deleted ones included, so a number is never reused). The package's own ``version``
  must equal it, else 409 ``TEMPLATE_VERSION_CONFLICT``.
- ``publish`` freezes a draft and emits ``report.template_published`` v1 in the same transaction;
  ``retire`` moves a published row to ``retired`` (kept for re-rendering, never deleted);
  ``delete_draft`` soft-deletes a draft only. Each refuses the wrong status with a 409.
- ``install_published`` is the config loader's path: insert as ``published`` with ``source =
  'config'`` and emit the same event.
- ``preview`` renders the stored sample data with the tenant's en-AU labels and display unit system,
  with the assets inlined as ``data:`` URIs.

The stored ``definition`` is ``template.json`` plus ``sampleData``; ``assets`` is ``{name:
{contentType, sha256, sizeBytes, dataBase64}}``.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Final
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine import repository as repo
from aip.modules.report_engine.events import REPORT_TEMPLATE_PUBLISHED, TemplatePublished
from aip.modules.report_engine.render import RenderContractError, inline_assets, render_html
from aip.modules.report_engine.schemas import (
    ReportTemplateDetail,
    ReportTemplatePage,
    ReportTemplateSummary,
    TemplateRow,
)
from aip.modules.report_engine.template_package import TemplatePackage
from aip.modules.terms.api import bulk_resolve, display_system
from aip.platform.context import get_context, new_request_id
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = ["PREVIEW_LOCALE", "TemplateService"]

PREVIEW_LOCALE: Final = "en-AU"
_PREVIEW_ZONE: Final = "UTC"  # unless the sample data names a ``timeZone``
_UNIQUE_VIOLATION: Final = "23505"

Row = dict[str, Any]


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _not_found(template_id: UUID) -> DomainError:
    return DomainError(404, "TEMPLATE_NOT_FOUND", detail=f"report template {template_id}")


def _row_values(package: TemplatePackage) -> dict[str, Any]:
    definition = package.definition
    return {
        "key": package.key,
        "version": package.version,
        "variant": package.variant,
        "record_type": package.record_type,
        "name_key": definition["nameKey"],
        "orientation": definition["orientation"],
        "paper": definition["paper"],
        "definition": {**definition, "sampleData": dict(package.sample_data)},
        "body": package.body,
        "css": package.css,
        "assets": {
            name: {
                "contentType": asset.content_type,
                "sha256": asset.sha256,
                "sizeBytes": len(asset.data),
                "dataBase64": base64.b64encode(asset.data).decode("ascii"),
            }
            for name, asset in sorted(package.assets.items())
        },
        "content_sha256": package.content_sha256,
    }


def encode_cursor(last_id: UUID) -> str:
    raw = json.dumps({"id": str(last_id)}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> UUID:
    """The id a cursor points after (422 ``INVALID_CURSOR`` when it is not one of ours)."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        return UUID(json.loads(raw)["id"])
    except (binascii.Error, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise DomainError(422, "INVALID_CURSOR") from None


class TemplateService:
    """Stateless; every method runs on the caller's tenant-bound connection."""

    async def _emit_published(self, conn: AsyncConnection, row: Row) -> None:
        payload = TemplatePublished(
            template_id=row["id"],
            key=row["key"],
            variant=row["variant"],
            version=row["version"],
            record_type=row["record_type"],
        ).model_dump(mode="json")
        await emit(
            conn, REPORT_TEMPLATE_PUBLISHED, 1, Aggregate("report_template", row["id"]), payload
        )

    async def create_draft(
        self, conn: AsyncConnection, actor: UUID | None, package: TemplatePackage
    ) -> Row:
        del actor  # drafts record no author yet; published_by records the publisher
        expected = await repo.lock_versions(conn, package.key, package.variant) + 1
        if package.version != expected:
            raise DomainError(409, "TEMPLATE_VERSION_CONFLICT", expectedVersion=expected)
        try:
            async with conn.begin_nested():
                return await repo.insert_template(
                    conn,
                    {
                        "id": _new_id(),
                        "tenant_id": get_context().tenant_id,
                        **_row_values(package),
                        "status": "draft",
                        "source": "upload",
                    },
                )
        except IntegrityError as exc:  # a concurrent first version of the same (key, variant)
            if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION:
                raise DomainError(409, "TEMPLATE_VERSION_CONFLICT") from None
            raise

    async def install_published(self, conn: AsyncConnection, package: TemplatePackage) -> Row:
        """Insert ``package`` as a published ``config`` template and emit the event (loader)."""
        row = await repo.insert_template(
            conn,
            {
                "id": _new_id(),
                "tenant_id": get_context().tenant_id,
                **_row_values(package),
                "status": "published",
                "source": "config",
                "published_at": func.now(),
            },
        )
        await self._emit_published(conn, row)
        return row

    async def publish(self, conn: AsyncConnection, actor: UUID | None, template_id: UUID) -> Row:
        row = await repo.lock(conn, template_id)
        if row is None:
            raise _not_found(template_id)
        if row["status"] != "draft":
            raise DomainError(409, "TEMPLATE_NOT_DRAFT")
        published = await repo.update_template(
            conn,
            template_id,
            {"status": "published", "published_at": func.now(), "published_by": actor},
        )
        await self._emit_published(conn, published)
        return published

    async def retire(self, conn: AsyncConnection, actor: UUID | None, template_id: UUID) -> Row:
        del actor
        row = await repo.lock(conn, template_id)
        if row is None:
            raise _not_found(template_id)
        if row["status"] != "published":
            raise DomainError(409, "TEMPLATE_NOT_PUBLISHED")
        return await repo.update_template(conn, template_id, {"status": "retired"})

    async def delete_draft(self, conn: AsyncConnection, template_id: UUID) -> None:
        row = await repo.lock(conn, template_id)
        if row is None:
            raise _not_found(template_id)
        if row["status"] != "draft":
            raise DomainError(409, "TEMPLATE_NOT_DRAFT")
        await repo.soft_delete_template(conn, template_id)

    async def get(self, conn: AsyncConnection, template_id: UUID) -> TemplateRow | None:
        """Any status, this tenant only; ``None`` when absent."""
        row = await repo.get(conn, template_id)
        return None if row is None else TemplateRow.model_validate(row)

    async def get_published(
        self, conn: AsyncConnection, key: str, variant: str
    ) -> TemplateRow | None:
        """The highest published version of ``(key, variant)``."""
        row = await repo.get_published(conn, key, variant)
        return None if row is None else TemplateRow.model_validate(row)

    async def detail(self, conn: AsyncConnection, template_id: UUID) -> ReportTemplateDetail:
        row = await repo.get(conn, template_id)
        if row is None:
            raise _not_found(template_id)
        return ReportTemplateDetail.from_row(row)

    async def list(
        self,
        conn: AsyncConnection,
        *,
        record_type: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ReportTemplatePage:
        after = None if cursor is None else decode_cursor(cursor)
        rows = await repo.list_templates(
            conn, record_type=record_type, status=status, after=after, limit=limit + 1
        )
        more = len(rows) > limit
        rows = rows[:limit]
        return ReportTemplatePage(
            items=[ReportTemplateSummary.model_validate(row) for row in rows],
            next_cursor=encode_cursor(rows[-1]["id"]) if more else None,
        )

    async def preview(self, conn: AsyncConnection, tenant_id: UUID, template_id: UUID) -> str:
        """The template rendered with its sample data, assets inlined (the API preview)."""
        template = await self.get(conn, template_id)
        if template is None:
            raise _not_found(template_id)
        keys = sorted(template.definition.get("termKeys", []))
        labels = await bulk_resolve(conn, keys, PREVIEW_LOCALE, tenant_id=tenant_id)
        system = await display_system(conn, tenant_id)
        sample = template.sample_data
        zone = sample.get("timeZone")
        try:
            document = render_html(
                template,
                sample,
                labels=labels,
                locale=PREVIEW_LOCALE,
                time_zone=zone if isinstance(zone, str) else _PREVIEW_ZONE,
                unit_system=system,
            )
        except RenderContractError as exc:
            raise DomainError(422, exc.code, detail=exc.detail) from None
        return inline_assets(document)
