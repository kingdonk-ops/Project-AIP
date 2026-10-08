"""The application's one SQLAlchemy ``AsyncEngine`` (DATABASE-02, ADR 0002).

It connects as ``aip_app`` (``DATABASE_URL``) through SQLAlchemy 2.0 Core on asyncpg. Nothing
outside ``aip.platform.db`` creates an engine or a connection (``tests/arch/
test_db_engine_boundary.py``); repositories receive the tenant-bound connection from
``with_tenant``.

Settings (environment):

- ``DATABASE_URL``: ``postgresql://aip_app:<password>@host:port/db``. The password comes from the
  environment / secrets manager, never from the repository.
- ``DB_POOL_MODE``: ``direct`` (default, a bounded asyncpg pool straight to Postgres) or
  ``pgbouncer`` (PgBouncer in transaction mode; see ``PGBOUNCER.md``). In ``pgbouncer`` mode the
  asyncpg statement caches are off and prepared statements get unique names, so a statement
  prepared on one server connection is never looked up on another.
- ``DB_POOL_SIZE`` (default 10), ``DB_MAX_OVERFLOW`` (default 0) and ``DB_POOL_TIMEOUT`` seconds
  (default 10): the pool bound. A request waits at most ``DB_POOL_TIMEOUT`` for a connection.

Every new physical connection is checked once. A login that is a superuser, has ``BYPASSRLS`` or
``CREATEROLE``, can use ``aip_owner``'s privileges, is in ``pg_write_all_data``, or owns the
database or a table could escape row-level security, so the engine refuses it with
``DatabaseConfigError`` (fail closed).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from aip.platform.db.errors import DatabaseConfigError

__all__ = [
    "DATABASE_URL_ENV",
    "EngineSettings",
    "PoolMode",
    "create_app_engine",
    "dispose_engine",
    "get_engine",
]

DATABASE_URL_ENV = "DATABASE_URL"
POOL_MODE_ENV = "DB_POOL_MODE"
POOL_SIZE_ENV = "DB_POOL_SIZE"
MAX_OVERFLOW_ENV = "DB_MAX_OVERFLOW"
POOL_TIMEOUT_ENV = "DB_POOL_TIMEOUT"
DEFAULT_POOL_SIZE = 10
DEFAULT_MAX_OVERFLOW = 0
DEFAULT_POOL_TIMEOUT = 10.0

# True when the login would escape RLS or could: a superuser, BYPASSRLS, CREATEROLE, a role that
# can use aip_owner's privileges or write every table (pg_write_all_data), the database owner,
# or the owner of any non-system relation (an owner can ALTER TABLE ... NO FORCE ROW LEVEL
# SECURITY). Roles are looked up by name so a cluster without aip_owner does not error.
_PRIVILEGE_CHECK = """
SELECT r.rolname::text,
       r.rolsuper OR r.rolbypassrls OR r.rolcreaterole
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_roles o
                  WHERE o.rolname = 'aip_owner' AND pg_has_role(r.oid, o.oid, 'USAGE'))
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_roles w
                  WHERE w.rolname = 'pg_write_all_data' AND pg_has_role(r.oid, w.oid, 'MEMBER'))
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_database d
                  WHERE d.datname = current_database() AND d.datdba = r.oid)
       OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                  WHERE c.relowner = r.oid
                    AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                    AND n.nspname NOT LIKE 'pg\\_%')
FROM pg_catalog.pg_roles r
WHERE r.rolname = current_user
"""


class PoolMode(StrEnum):
    DIRECT = "direct"
    PGBOUNCER = "pgbouncer"


@dataclass(frozen=True, slots=True)
class EngineSettings:
    url: str
    pool_mode: PoolMode = PoolMode.DIRECT
    pool_size: int = DEFAULT_POOL_SIZE
    max_overflow: int = DEFAULT_MAX_OVERFLOW
    pool_timeout: float = DEFAULT_POOL_TIMEOUT

    def __post_init__(self) -> None:
        if self.pool_size < 1:
            raise DatabaseConfigError(f"{POOL_SIZE_ENV} must be at least 1")
        if self.max_overflow < 0:
            raise DatabaseConfigError(f"{MAX_OVERFLOW_ENV} must not be negative")
        if self.pool_timeout <= 0:
            raise DatabaseConfigError(f"{POOL_TIMEOUT_ENV} must be positive")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> EngineSettings:
        env = os.environ if environ is None else environ
        url = env.get(DATABASE_URL_ENV, "")
        if not url:
            raise DatabaseConfigError(f"{DATABASE_URL_ENV} is not set")
        raw_mode = env.get(POOL_MODE_ENV, PoolMode.DIRECT.value).strip().lower()
        try:
            mode = PoolMode(raw_mode)
        except ValueError:
            allowed = ", ".join(m.value for m in PoolMode)
            raise DatabaseConfigError(f"{POOL_MODE_ENV} must be one of {allowed}") from None
        return cls(
            url=url,
            pool_mode=mode,
            pool_size=_int(env, POOL_SIZE_ENV, DEFAULT_POOL_SIZE),
            max_overflow=_int(env, MAX_OVERFLOW_ENV, DEFAULT_MAX_OVERFLOW),
            pool_timeout=_float(env, POOL_TIMEOUT_ENV, DEFAULT_POOL_TIMEOUT),
        )


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise DatabaseConfigError(f"{key} must be an integer") from None


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise DatabaseConfigError(f"{key} must be a number") from None


def _unique_statement_name() -> str:
    return f"__asyncpg_{uuid.uuid4().hex}__"


def connect_args(mode: PoolMode) -> dict[str, Any]:
    """asyncpg connect arguments for ``mode`` (PgBouncer: no statement caches, unique names)."""
    if mode is PoolMode.PGBOUNCER:
        return {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": _unique_statement_name,
        }
    return {}


def _async_url(url: str) -> str:
    try:
        parsed = make_url(url)
    except ArgumentError:
        raise DatabaseConfigError(f"{DATABASE_URL_ENV} is not a valid database URL") from None
    if parsed.get_backend_name() != "postgresql":
        raise DatabaseConfigError(f"{DATABASE_URL_ENV} must be a postgresql:// URL")
    return parsed.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


def _refuse_privileged_login(dbapi_connection: Any, _record: Any) -> None:
    """Pool ``connect`` hook: refuse a login that would bypass row-level security."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(_PRIVILEGE_CHECK)
        row = cursor.fetchone()
    finally:
        cursor.close()
    dbapi_connection.rollback()
    if row is None or bool(row[1]):
        user = "unknown" if row is None else str(row[0])
        raise DatabaseConfigError(
            f"refusing to use role {user!r} for application traffic: it is a superuser, can "
            "bypass RLS, create roles, act as aip_owner, write every table or owns objects "
            "(use aip_app)"
        )


def create_app_engine(settings: EngineSettings) -> AsyncEngine:
    """Build a bounded engine for ``settings``. Callers outside tests use ``get_engine()``."""
    engine = create_async_engine(
        _async_url(settings.url),
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout,
        pool_recycle=1800,
        connect_args=connect_args(settings.pool_mode),
    )
    event.listen(engine.sync_engine, "connect", _refuse_privileged_login)
    return engine


_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """The process-wide engine, built from the environment on first use."""
    global _engine
    if _engine is None:
        _engine = create_app_engine(EngineSettings.from_env())
    return _engine


async def dispose_engine() -> None:
    """Close the process-wide engine's pool (application shutdown, tests)."""
    global _engine
    engine, _engine = _engine, None
    if engine is not None:
        await engine.dispose()
