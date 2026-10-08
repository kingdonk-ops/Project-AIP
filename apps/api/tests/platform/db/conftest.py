"""Re-exports the shared Postgres fixtures, which now live in ``tests/fixtures/postgres.py``.

Kept so existing ``from tests.platform.db.conftest import ...`` lines keep working; new code
imports from ``tests.fixtures.postgres``.
"""

from __future__ import annotations

from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures and helpers
    API_DIR,
    APP,
    BOOTSTRAP_SQL,
    JOBS,
    OWNER,
    OWNER_PASSWORD,
    PG_IMAGE,
    READONLY,
    REPO_ROOT,
    ROLE_PASSWORDS,
    FreshDb,
    _docker_reachable,  # pyright: ignore[reportPrivateUsage]
    aip_db_command,
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    execute,
    fetch,
    migrated_db,  # pyright: ignore[reportUnusedImport]
    migrations_copy,  # pyright: ignore[reportUnusedImport]
    owner_conn_for_seeding_only,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
    with_db,
)
