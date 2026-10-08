"""Data access for identity: the pre-tenant login directory (IDENTITY-01, ADR 0005).

Reads go only through the SECURITY DEFINER function ``identity_resolve_login``; ``aip_app`` cannot
select from ``login_directory``. This runs before any tenant is known, so it uses the platform's
``before_tenant()`` connection (``aip_app``, no tenant set) instead of ``with_tenant``.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.db.session import before_tenant

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


Connect = Callable[[], AbstractAsyncContextManager[AsyncConnection]]


class SqlLoginDirectory:
    """``LoginDirectory`` over Postgres; ``connect`` defaults to the platform's ``before_tenant``."""

    def __init__(self, connect: Connect = before_tenant) -> None:
        self._connect = connect

    async def resolve(self, kind: LookupKind, key: str) -> LoginTarget | None:
        async with self._connect() as conn:
            return await resolve_login(conn, kind, key)
