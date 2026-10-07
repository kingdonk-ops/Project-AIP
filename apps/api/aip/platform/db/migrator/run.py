"""``aip-db migrate``: ``alembic upgrade head`` as ``aip_owner``, serialised by an advisory lock.

There is no downgrade command: revisions are forward-only (ADR 0002).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import NullPool, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.util import await_only

OWNER_ROLE = "aip_owner"
OWNER_ERROR = "migrator must run as aip_owner"
URL_ENV = "DATABASE_MIGRATOR_URL"
_LOCK = "SELECT pg_advisory_lock(hashtext('aip_migrations'))"
_UNLOCK = "SELECT pg_advisory_unlock(hashtext('aip_migrations'))"


class MigratorError(RuntimeError):
    """A refusal the CLI reports as one line with exit code 1."""


def migrator_url(environ: Mapping[str, str] | None = None) -> str:
    """The direct (never PgBouncer) connection URL for ``aip_owner``."""
    env = os.environ if environ is None else environ
    url = env.get(URL_ENV, "")
    if not url:
        raise MigratorError(f"{URL_ENV} is not set")
    return url


def to_async_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


def to_libpq_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def create_migrator_engine(url: str) -> AsyncEngine:
    return create_async_engine(to_async_url(url), poolclass=NullPool)


def prepare_connection(connection: Connection) -> None:
    """Refuse any role but ``aip_owner``, then take the session-level migration lock."""
    user = connection.execute(text("SELECT current_user")).scalar_one()
    if user != OWNER_ROLE:
        connection.rollback()
        raise MigratorError(OWNER_ERROR)
    connection.execute(text(_LOCK))
    # Commit so Alembic starts from a clean connection; the session-level lock survives it.
    connection.commit()


def release_lock(connection: Connection) -> None:
    if connection.in_transaction():
        connection.rollback()
    connection.execute(text(_UNLOCK))
    connection.commit()


def use_simple_query_protocol(context: MigrationContext) -> None:
    """Run ``op.execute("<raw SQL>")`` through asyncpg's simple query protocol.

    SQLAlchemy's asyncpg adapter prepares every statement, which rejects multi-statement SQL.
    Revisions are raw SQL scripts, so plain strings go to the driver connection directly, inside
    the transaction Alembic opened for the revision (or in autocommit inside autocommit_block).
    """
    connection = context.connection
    if connection is None:
        return
    conn: Connection = connection
    impl: Any = context.impl
    original = impl.execute

    def execute(sql: object, execution_options: object = None) -> None:
        if not isinstance(sql, str):
            original(sql, execution_options)
            return
        # Any statement through SQLAlchemy makes the adapter open its pending transaction
        # (a no-op under AUTOCOMMIT), so the raw script runs inside it.
        conn.exec_driver_sql("SELECT 1")
        driver: Any = conn.connection.driver_connection
        await_only(driver.execute(sql))

    setattr(impl, "execute", execute)  # noqa: B010


def migrate(config_path: Path) -> None:
    """``alembic upgrade head`` with the given ``alembic.ini``."""
    migrator_url()  # fail fast with a clear message
    command.upgrade(Config(str(config_path)), "head")
