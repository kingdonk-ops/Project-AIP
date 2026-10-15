"""Published interface of the terms module.

Other modules may import only this file. Keep it small and stable.

``resolve`` and ``bulk_resolve`` (TERMS-02) resolve dictionary keys through the fallback chain on
the caller's ``with_tenant`` connection. Platform code reaches the same resolver through the
``aip.platform.terms`` port, which :func:`install` registers at startup.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.terms import register_term_resolver

from .service import bulk_resolve, resolve

__all__ = ["ModuleApi", "bulk_resolve", "get_api", "install", "resolve"]


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


class _TermsApi:
    resolve = staticmethod(resolve)
    bulk_resolve = staticmethod(bulk_resolve)


_API = _TermsApi()


def get_api() -> ModuleApi:
    """Return the terms module's published interface."""
    return _API


def install() -> None:
    """Register this module's resolver with the ``aip.platform.terms`` port (at startup)."""
    register_term_resolver(_API)
