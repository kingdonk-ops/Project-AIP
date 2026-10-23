"""``with_principal`` / ``run_as_system``: bind a principal onto a tenant transaction (ACCESS-03).

The project-scope RLS predicate ``access_project_visible`` reads ``app.user_id`` and
``app.principal_kind`` (set transaction-locally, like ``app.tenant_id`` in ADR 0002).
``with_tenant`` already sets both for a ``RequestContext`` that names a user, so ordinary request
handlers get user scope for free. These helpers are the *explicit* form, for the two cases a bare
request context cannot express:

- ``with_principal(principal)`` wraps ``with_tenant`` and binds a ``ScopePrincipal``: a ``user``
  (sets ``app.user_id``), an ``api_client`` (tenant-wide, no user id, IDENTITY-06) or a ``system``
  principal. A ``system``/``api_client`` ``app.principal_kind`` makes ``access_project_visible``
  true for every project in the tenant (tenant-wide by design).
- ``run_as_system(tenant)`` is the worker form: a ``system`` principal, so a background job sees
  all of a tenant's project-scoped rows (it never acts "as" one user). It never crosses tenants.

They live in ``aip.platform.db`` next to ``with_tenant`` because only this package may open database
connections (ADR 0002) and because ``aip.platform`` must not import ``aip.modules`` (ARCH-03); the
access module re-exports them from ``aip.modules.access.api`` for other modules to use.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aip.platform.db.session import TenantRef, tenant_uuid, with_tenant

__all__ = [
    "PrincipalKind",
    "ScopePrincipal",
    "SetConfig",
    "run_as_system",
    "set_config_statements",
    "with_principal",
]

PrincipalKind = Literal["user", "api_client", "system"]


@dataclass(frozen=True, slots=True)
class ScopePrincipal:
    """Who a transaction acts as, for RLS. A ``user`` carries a ``user_id``; the others do not."""

    tenant_id: UUID
    kind: PrincipalKind = "user"
    user_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.kind == "user" and self.user_id is None:
            raise ValueError("a user principal needs a user_id")
        if self.kind != "user" and self.user_id is not None:
            raise ValueError(f"a {self.kind} principal carries no user_id")


@dataclass(frozen=True, slots=True)
class SetConfig:
    """One ``set_config(setting, value, is_local)`` to run; ``is_local`` is transaction-local."""

    setting: str
    value: str
    is_local: bool = True


def set_config_statements(principal: ScopePrincipal) -> list[SetConfig]:
    """The ``set_config`` calls binding ``principal`` onto the transaction (all transaction-local).

    Always ``app.tenant_id`` and ``app.principal_kind``; ``app.user_id`` only for a ``user``
    principal (an ``api_client`` or ``system`` principal sets no user id).
    """
    statements = [
        SetConfig("app.tenant_id", str(principal.tenant_id)),
        SetConfig("app.principal_kind", principal.kind),
    ]
    if principal.kind == "user":
        assert principal.user_id is not None  # guaranteed by __post_init__
        statements.append(SetConfig("app.user_id", str(principal.user_id)))
    return statements


# The value is always a bind parameter, never interpolated: a principal id can never be SQL. There
# is deliberately no setter for ``app.tenant_id``: ``with_tenant`` is the one place that sets the
# tenant (DATABASE-07 boundary), and ``with_principal`` runs inside it.
_SETTERS = {
    "app.principal_kind": text("SELECT set_config('app.principal_kind', :value, true)"),
    "app.user_id": text("SELECT set_config('app.user_id', :value, true)"),
}


async def _apply(conn: AsyncConnection, principal: ScopePrincipal) -> None:
    # app.tenant_id is left to with_tenant; set_config_statements still reports it for callers.
    for statement in set_config_statements(principal):
        setter = _SETTERS.get(statement.setting)
        if setter is not None:
            await conn.execute(setter, {"value": statement.value})


@asynccontextmanager
async def with_principal(
    principal: ScopePrincipal, *, engine: AsyncEngine | None = None
) -> AsyncGenerator[AsyncConnection]:
    """Yield a ``with_tenant`` connection for ``principal.tenant_id`` with the principal bound.

    The session guard uses this after a user is verified; ``engine`` defaults to the ``aip_app``
    engine, and tests pass their own.
    """
    async with with_tenant(principal.tenant_id, engine=engine) as conn:
        await _apply(conn, principal)
        yield conn


@asynccontextmanager
async def run_as_system(
    tenant: TenantRef, *, engine: AsyncEngine | None = None
) -> AsyncGenerator[AsyncConnection]:
    """Yield a ``with_tenant`` connection bound to a ``system`` principal, for worker jobs.

    A system principal sees every project-scoped row in ``tenant`` (tenant-wide), never one user's
    slice, and never another tenant's rows. ``tenant`` is a UUID, UUID string or request context.
    """
    principal = ScopePrincipal(tenant_id=tenant_uuid(tenant), kind="system")
    async with with_principal(principal, engine=engine) as conn:
        yield conn
