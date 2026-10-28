"""Published interface of the report_engine module (REPORTS-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the read joins their transaction and RLS applies.

``ReportTemplatesApi.get_published`` gives the highest published version of a template key and
variant; ``get`` any version by id (a retired one too, so a pinned report can be re-rendered).
``render_html`` is the render contract: a template plus a plain data dict, resolved labels, a
locale, an IANA time zone and a unit system give a ``RenderedDocument`` (inert HTML, its asset
files and the ``PageSpec`` for Gotenberg) or a ``RenderContractError``. In R1 only report_engine's
own render job (REPORTS-02) calls it; no other module builds PDF HTML.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine.render import (
    Margins,
    PageSpec,
    RenderContractError,
    RenderedDocument,
    render_html,
)
from aip.modules.report_engine.schemas import TemplateRow
from aip.modules.report_engine.service import TemplateService

__all__ = [
    "Margins",
    "PageSpec",
    "RenderContractError",
    "RenderedDocument",
    "ReportTemplatesApi",
    "TemplateRow",
    "render_html",
]

_service = TemplateService()


class ReportTemplatesApi:
    """The template reads report_engine offers to other modules."""

    async def get_published(
        self, conn: AsyncConnection, key: str, variant: str
    ) -> TemplateRow | None:
        """The highest published version of ``(key, variant)`` in this tenant, or ``None``."""
        return await _service.get_published(conn, key, variant)

    async def get(self, conn: AsyncConnection, template_id: UUID) -> TemplateRow | None:
        """The template ``template_id`` in any status in this tenant, or ``None``."""
        return await _service.get(conn, template_id)
