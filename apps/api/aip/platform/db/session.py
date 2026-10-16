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

``after_commit(conn, hook)`` registers an async hook that runs once the transaction has really
committed (not on rollback): use it for cache invalidation. SQLAlchemy's ``commit`` event fires
*before* the database commit, so a cache bumped there can be refilled with the old rows.

Do not nest ``with_tenant`` calls. Each call takes its own connection and transaction, so an
inner call needs a second connection while the outer one is still held. With a small pool and
``max_overflow=0`` (the default), concurrent requests that each hold one connection and wait for
a second can stall until ``DB_POOL_TIMEOUT``. Pass the outer ``conn`` down instead.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from aip.platform.context import RequestContext
from aip.platform.db.engine import (
    EngineSettings,
    _async_url,  # pyright: ignore[reportPrivateUsage]
    create_app_engine,
    get_audit_writer_engine,
    get_engine,
)
from aip.platform.db.errors import InvalidTenantError
from aip.platform.db.tls import DbTls

__all__ = [
    "PLATFORM_TENANT_ID",
    "AfterCommitHook",
    "DbEngine",
    "JobsRoleError",
    "NoTransactionHookError",
    "PlatformTenantError",
    "TenantRef",
    "after_commit",
    "app_engine_for",
    "as_jobs_role",
    "audit_writer_tenant",
    "before_tenant",
    "cross_tenant_readonly",
    "tenant_uuid",
    "with_platform_tenant",
    "with_tenant",
]

TenantRef = UUID | str | RequestContext
AfterCommitHook = Callable[[], Awaitable[None]]

logger = structlog.stdlib.get_logger(__name__)
_AFTER_COMMIT = "aip.after_commit_hooks"


class NoTransactionHookError(RuntimeError):
    """``after_commit`` was called on a connection not opened by ``with_tenant``."""


def after_commit(conn: AsyncConnection, hook: AfterCommitHook) -> None:
    """Run ``hook`` after ``with_tenant``'s transaction on ``conn`` commits (never on rollback).

    A failing hook is logged, not raised: the data is already committed.
    """
    hooks: list[AfterCommitHook] | None = conn.info.get(_AFTER_COMMIT)
    if hooks is None:
        raise NoTransactionHookError("after_commit needs a with_tenant connection")
    hooks.append(hook)


# ADR 0028: the reserved tenant of platform rows (terms defaults, built-in packs). Not a row in
# ``tenants``; ``with_tenant`` refuses it, so only ``with_platform_tenant`` (as aip_owner) binds it.
PLATFORM_TENANT_ID = UUID(int=0)
_PLATFORM_WRITER = "aip_owner"

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")
_JOBS_ROLE = "aip_jobs"

DbEngine = AsyncEngine
"""The engine type, for code outside ``aip.platform.db`` that is handed an engine to pass on."""


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
    hooks: list[AfterCommitHook] = []
    async with bound.begin() as conn:
        await conn.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
        conn.info[_AFTER_COMMIT] = hooks  # conn.info outlives the checkout: always removed
        try:
            yield conn
        finally:
            conn.info.pop(_AFTER_COMMIT, None)
    for hook in hooks:  # reached only when the commit succeeded
        try:
            await hook()
        except Exception:
            logger.warning("db.after_commit_hook_failed", exc_info=True)


@asynccontextmanager
async def audit_writer_tenant(
    tenant: TenantRef, *, engine: AsyncEngine | None = None
) -> AsyncGenerator[AsyncConnection]:
    """Yield an ``aip_audit_writer`` connection in a transaction bound to ``tenant`` (AUDIT-01).

    This is the only connection that may INSERT into ``audit_log`` and maintain the chain heads and
    checkpoints. It behaves like ``with_tenant`` — validates the tenant id, opens a transaction and
    sets ``app.tenant_id`` transaction-locally so RLS applies — but on the audit-writer engine
    instead of the ``aip_app`` one. The repository's ``append_audit_entries`` takes the connection
    this yields. ``engine`` defaults to the process-wide audit-writer engine; tests pass their own.
    """
    tenant_id = tenant_uuid(tenant)  # before any pool checkout
    bound = get_audit_writer_engine() if engine is None else engine
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


class PlatformTenantError(RuntimeError):
    """``with_platform_tenant`` was given an engine that does not log in as ``aip_owner``."""


@asynccontextmanager
async def with_platform_tenant(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """Yield an ``aip_owner`` connection in a transaction bound to ``PLATFORM_TENANT_ID``.

    For deploy-time loaders of platform rows (``python -m aip.modules.terms.loader``). The engine
    comes from ``create_migrator_engine(DATABASE_MIGRATOR_URL)``; any other login is refused
    before the tenant is set, because the platform-row policies let only ``aip_owner`` write.
    """
    async with engine.begin() as conn:
        user = (await conn.execute(text("SELECT current_user"))).scalar_one()
        if user != _PLATFORM_WRITER:
            raise PlatformTenantError(
                f"platform rows are written as {_PLATFORM_WRITER}, not {user}"
            )
        await conn.execute(_SET_TENANT, {"tenant_id": str(PLATFORM_TENANT_ID)})
        yield conn


class JobsRoleError(RuntimeError):
    """``as_jobs_role`` was given an engine that does not log in as ``aip_jobs``."""


@asynccontextmanager
async def as_jobs_role(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """Yield an ``aip_jobs`` connection in a transaction with no tenant bound (ADR 0003, 0030).

    Only for the outbox dispatcher's cross-tenant claim and outcome writes: ``aip_jobs`` reads every
    tenant's ``domain_events`` through its own policies and may update only the dispatch columns.
    The engine comes from ``get_jobs_engine()`` (tests pass their own); any other login is refused
    before a statement runs, so this can never become a tenant-less ``aip_app`` connection.
    """
    async with engine.begin() as conn:
        user = (await conn.execute(text("SELECT current_user"))).scalar_one()
        if user != _JOBS_ROLE:
            raise JobsRoleError(f"the outbox dispatcher runs as {_JOBS_ROLE}, not {user}")
        yield conn


@asynccontextmanager
async def app_engine_for(url: str) -> AsyncGenerator[AsyncEngine]:
    """A separate bounded ``aip_app`` engine on ``url`` (say a read replica), disposed on exit.

    Use it only as ``with_tenant(tenant, engine=...)``, so RLS still applies. ENT-01's database-size
    estimate reads from a replica this way (``ENTITLEMENTS_DB_ESTIMATE_URL``). A privileged login is
    refused, as for the main engine.
    """
    engine = create_app_engine(EngineSettings(url=url, pool_size=1, max_overflow=0))
    try:
        yield engine
    finally:
        await engine.dispose()


@asynccontextmanager
async def cross_tenant_readonly(url: str) -> AsyncGenerator[AsyncConnection]:
    """A short READ ONLY transaction on ``url`` with no tenant bound, for approved aggregates only.

    It exists for ENT-01's ``single_pass`` database-size estimate (ADR 0008 amendment), which needs
    a role that reads across tenants. No such role exists until the owner approves one in an ADR,
    so nothing configures it by default. The transaction is read-only and always rolled back; the
    caller may return only aggregates (tenant id and byte counts), never rows.
    """
    engine = create_async_engine(
        _async_url(url),
        pool_size=1,
        max_overflow=0,
        connect_args=DbTls.from_env().asyncpg_connect_args(),
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            try:
                yield conn
            finally:
                await conn.rollback()
    finally:
        await engine.dispose()
