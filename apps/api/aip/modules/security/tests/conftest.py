"""Fixtures for the security tests: a migrated database and an ``aip_app`` engine."""

from __future__ import annotations

from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)
