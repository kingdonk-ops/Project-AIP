"""Alembic environment (DATABASE-08, ADR 0002): async, asyncpg, forward-only raw SQL.

- The URL comes from ``DATABASE_MIGRATOR_URL``: a direct connection, never through PgBouncer.
- It refuses to run unless ``current_user`` is ``aip_owner``.
- ``pg_advisory_lock(hashtext('aip_migrations'))`` serialises concurrent runs.
- No ``target_metadata``: autogenerate is not used (``aip-db check-schema`` compares instead).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from aip.platform.db.migrator.run import (
    create_migrator_engine,
    migrator_url,
    prepare_connection,
    release_lock,
    use_simple_query_protocol,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _run_sync(connection: Connection) -> None:
    prepare_connection(connection)
    try:
        context.configure(
            connection=connection,
            target_metadata=None,
            version_table_schema=config.get_main_option("version_table_schema", "aip_meta"),
            transaction_per_migration=True,
        )
        use_simple_query_protocol(context.get_context())
        context.run_migrations()
    finally:
        release_lock(connection)


async def _run_async() -> None:
    engine = create_migrator_engine(migrator_url())
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline (--sql) migrations are not supported; run aip-db migrate")

asyncio.run(_run_async())
