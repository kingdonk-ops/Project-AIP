"""Fixtures for the terms tests: a migrated database and the ``aip_app`` connection.

Platform rows are loaded with ``load(..., url=<aip_owner URL>)``; every assertion goes through
``tenant_db`` (``aip_app``, RLS on).
"""

from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)
from tests.fixtures.redis import (
    redis_server,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
