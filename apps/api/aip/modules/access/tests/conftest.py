"""Shared real-Postgres fixtures for the access module tests (TESTING-01)."""

from tests.fixtures.postgres import (  # noqa: F401 - shared real-Postgres fixtures (TESTING-01)
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)
