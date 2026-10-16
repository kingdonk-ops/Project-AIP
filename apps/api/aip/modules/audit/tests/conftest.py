"""Fixtures for the audit integration tests (AUDIT-01).

Real Postgres only (TESTING-01): a database migrated to head with the real roles. ``audit_log``
has no FK to ``tenants``, so tests use the fixture tenant UUIDs directly without seeding rows — RLS
only compares ``tenant_id`` with ``app.tenant_id``.

The audit writer engine and the raw owner/superuser connections live in
``tests.fixtures.postgres`` (outside ``aip/``), because the DB-engine boundary scan forbids
creating engines or connections anywhere under ``aip/``, module tests included.
"""

from __future__ import annotations

from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures and helpers
    Writer,
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    db_connection,
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    outbox,  # pyright: ignore[reportUnusedImport]
    owner_conn_with_tenant,
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
    writer,  # pyright: ignore[reportUnusedImport]
)

__all__ = ["Writer", "db_connection", "owner_conn_with_tenant"]
