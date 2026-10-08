"""``with_tenant``: the only way application code gets a database connection (ADR 0002).

::

    async with with_tenant(get_context()) as conn:
        rows = (await conn.execute(select(widgets))).all()

It validates the tenant id first and raises ``InvalidTenantError`` before taking a connection
from the pool. Then it opens a transaction, sets ``app.tenant_id`` with
``set_config('app.tenant_id', <tenant>, true)`` and yields the ``AsyncConnection``. The ``true``
makes the setting transaction-local: it ends with the commit (on normal exit) or the rollback (on
an exception), so it never leaks to the next user of a pooled connection, or of a PgBouncer
server connection. Session-level settings of the tenant are banned (a test scans ``aip/``).

Code that commits inside the block cannot keep going: SQLAlchemy refuses further statements on
the closed ``begin()`` transaction. Any connection used without a tenant set fails closed under
RLS anyway: 0 rows, and writes are rejected.

Do not nest ``with_tenant`` calls. Each call takes its own connection and transaction, so an
inner call needs a second connection while the outer one is still held. With a small pool and
``max_overflow=0`` (the default), concurrent requests that each hold one connection and wait for
a second can stall until ``DB_POOL_TIMEOUT``. Pass the outer ``conn`` down instead.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aip.platform.context import RequestContext
from aip.platform.db.engine import get_engine
from aip.platform.db.errors import InvalidTenantError

__all__ = ["TenantRef", "before_tenant", "tenant_uuid", "with_tenant"]

TenantRef = UUID | str | RequestContext

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")


def tenant_uuid(tenant: object) -> UUID:
    """The tenant id of ``tenant`` (a UUID, a UUID string or a ``RequestContext``)."""
    if isinstance(tenant, RequestContext):
        value: object = tenant.tenant_id
    else:
        value = tenant
    if isinstance(value, str):
        try:
            value = UUID(value)
        except ValueError:
            raise InvalidTenantError("tenant id is not a UUID") from None
    if not isinstance(value, UUID):
        raise InvalidTenantError(f"tenant id must be a UUID, not {type(value).__name__}")
    if value.int == 0:
        raise InvalidTenantError("the nil UUID is not a tenant id")
    return value


@asynccontextmanager
async def with_tenant(
    tenant: TenantRef, *, engine: AsyncEngine | None = None
) -> AsyncGenerator[AsyncConnection]:
    """Yield a connection in a transaction bound to ``tenant``; commit on exit, roll back on error.

    ``engine`` defaults to the process-wide ``aip_app`` engine; tests pass their own.
    """
    tenant_id = tenant_uuid(tenant)  # before any pool checkout
    bound = get_engine() if engine is None else engine
    async with bound.begin() as conn:
        await conn.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
        yield conn


@asynccontextmanager
async def before_tenant(*, engine: AsyncEngine | None = None) -> AsyncGenerator[AsyncConnection]:
    """Yield an ``aip_app`` connection with no tenant set, for the pre-tenant lookups only.

    Sign-in resolves the tenant before one is known (ADR 0005): ``identity_resolve_login`` reads
    the global ``login_directory`` through a SECURITY DEFINER function, and ``aip_app`` has no
    privilege on the table itself. Every tenant table still fails closed here (no
    ``app.tenant_id``: 0 rows, writes rejected), so this cannot read tenant data. Anything else
    uses ``with_tenant``.
    """
    bound = get_engine() if engine is None else engine
    async with bound.begin() as conn:
        yield conn
