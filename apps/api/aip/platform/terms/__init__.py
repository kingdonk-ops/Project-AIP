"""The terminology port: ``TermResolver`` and its registration hook (TERMS-02, ADR 0004).

Platform code (emails, PDFs, exports) formats user-facing text without importing a module::

    from aip.platform.terms import term_resolver

    label = await term_resolver().resolve(conn, "itp.point_type.hold", "en-AU", tenant_id=t)

The terms module registers its implementation at startup (``aip.main`` and the worker call
``aip.modules.terms.api.install``). This package imports no module.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "TermResolver",
    "TermResolverMissingError",
    "register_term_resolver",
    "term_resolver",
]


class TermResolver(Protocol):
    """Resolve dictionary keys for a tenant, client and project on a ``with_tenant`` connection."""

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


class TermResolverMissingError(RuntimeError):
    """No resolver is registered (the terms module is not loaded in this process)."""


_resolver: TermResolver | None = None


def register_term_resolver(resolver: TermResolver | None) -> None:
    """Register (or with ``None``, clear) the process-wide resolver."""
    global _resolver
    _resolver = resolver


def term_resolver() -> TermResolver:
    """The registered resolver; raises :class:`TermResolverMissingError` if there is none."""
    if _resolver is None:
        raise TermResolverMissingError(
            "no TermResolver is registered: the terms module is not loaded"
        )
    return _resolver
