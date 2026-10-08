"""Data access for identity: the pre-tenant login directory (IDENTITY-01, ADR 0005).

Reads go only through the SECURITY DEFINER function ``identity_resolve_login``; ``aip_app`` cannot
select from ``login_directory``. This runs before any tenant is known, so it does not use
``with_tenant``.

Until DATABASE-02 lands ``aip.platform.db.engine``, ``SqlLoginDirectory.from_url`` builds a small
dedicated engine from ``DATABASE_URL``; switch it to the platform engine then.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

LookupKind = Literal["email_domain", "tenant_slug"]

_RESOLVE = text("SELECT tenant_id, idp_alias FROM identity_resolve_login(:kind, :key)")


@dataclass(frozen=True)
class LoginTarget:
    tenant_id: UUID
    idp_alias: str | None


class LoginDirectory(Protocol):
    async def resolve(self, kind: LookupKind, key: str) -> LoginTarget | None: ...


async def resolve_login(conn: AsyncConnection, kind: LookupKind, key: str) -> LoginTarget | None:
    row = (await conn.execute(_RESOLVE, {"kind": kind, "key": key})).first()
    if row is None:
        return None
    return LoginTarget(tenant_id=row[0], idp_alias=row[1])


def async_database_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


class SqlLoginDirectory:
    """``LoginDirectory`` over Postgres."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @classmethod
    def from_url(cls, url: str) -> SqlLoginDirectory:
        return cls(create_async_engine(async_database_url(url), pool_size=2, max_overflow=2, pool_pre_ping=True))

    async def resolve(self, kind: LookupKind, key: str) -> LoginTarget | None:
        async with self._engine.connect() as conn:
            return await resolve_login(conn, kind, key)

    async def dispose(self) -> None:
        await self._engine.dispose()
