"""Published interface of the terms module.

Other modules may import only this file. Keep it small and stable.

``resolve`` and ``bulk_resolve`` (TERMS-02) resolve dictionary keys through the fallback chain on
the caller's ``with_tenant`` connection. Platform code reaches the same resolver through the
``aip.platform.terms`` port, which :func:`install` registers at startup.

``format_message`` resolves a key and formats it as an ICU message; ``display_system``,
``to_display`` and ``to_si`` convert between SI storage and display units; ``template_environment``,
``template_scope`` and ``render_template`` give email and PDF templates the ``t`` and
``fmt_measure`` filters (TERMS-03).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.terms import register_term_resolver

from .icu import MessageFormatError, format_message
from .service import bulk_resolve, resolve
from .templating import (
    TemplateScope,
    register_filters,
    render_template,
    template_environment,
    template_scope,
)
from .units import Quantity, UnitSystem, UnknownUnitError, display_system, to_display, to_si

__all__ = [
    "MessageFormatError",
    "ModuleApi",
    "Quantity",
    "TemplateScope",
    "UnitSystem",
    "UnknownUnitError",
    "bulk_resolve",
    "display_system",
    "format_message",
    "get_api",
    "install",
    "register_filters",
    "render_template",
    "resolve",
    "template_environment",
    "template_scope",
    "to_display",
    "to_si",
]


class ModuleApi(Protocol):
    """The operations terms offers to other modules."""

    async def resolve(
        self,
        conn: AsyncConnection,
        key: str,
        locale: str,
        *,
        tenant_id: UUID,
        client_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> str: ...

    async def bulk_resolve(
        self,
        conn: AsyncConnection,
        keys: Iterable[str] | None,
        locale: str,
        *,
        tenant_id: UUID,
        client_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> dict[str, str]: ...

    async def format_message(
        self,
        conn: AsyncConnection,
        key: str,
        args: Mapping[str, Any],
        locale: str,
        *,
        tenant_id: UUID,
        client_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> str: ...

    async def display_system(
        self, conn: AsyncConnection, tenant_id: UUID, project_id: UUID | None = None
    ) -> UnitSystem: ...


class _TermsApi:
    resolve = staticmethod(resolve)
    bulk_resolve = staticmethod(bulk_resolve)
    format_message = staticmethod(format_message)
    display_system = staticmethod(display_system)


_API = _TermsApi()


def get_api() -> ModuleApi:
    """Return the terms module's published interface."""
    return _API


def install() -> None:
    """Register this module's resolver with the ``aip.platform.terms`` port (at startup)."""
    register_term_resolver(_API)
