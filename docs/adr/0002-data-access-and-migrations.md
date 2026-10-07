# ADR 0002: SQLAlchemy Core + Alembic raw-SQL migrations; tenant context via SET LOCAL

- **Status:** accepted (matches owner decision "Keep Alembic raw SQL with templates")
- **Date:** 2026-10-07 (revised for the Python backend; the first version chose Kysely)
- **Affects:** database and every module with tables; DATABASE-*, TESTING-01, TESTING-05, OPS-01

## Decision

- **Query layer:** SQLAlchemy 2.0 **Core** (not the ORM unit-of-work) on `asyncpg`. Tables are declared in each
  module's `tables.py`, and repositories in `repository.py`. Raw SQL is allowed via `text()` for ltree, pgvector,
  FTS and RLS helpers.
- **Migrations:** Alembic, **forward-only** revisions written as raw SQL (`op.execute`) from templates in
  `db/templates/` (tenant table, append-only table). They run as the migrator role. There is no autogenerate
  for RLS or grants. A CI test compares the migrated schema to the declared tables.
- **Tenant context:** every request runs inside `async with with_tenant(ctx) as conn:`. That opens a transaction and
  runs `select set_config('app.tenant_id', :t, true)`. Session-level `SET` is banned. Policies use
  `NULLIF(current_setting('app.tenant_id', true), '')::uuid` with both `USING` and `WITH CHECK`, so an unset context fails closed.
- **Roles:** `aip_owner` (migrations only), `aip_app` (no BYPASSRLS and not the owner), `aip_jobs` (Procrastinate
  tables plus the outbox publish columns), `aip_readonly` (reporting).
- **Pooling:** a bounded asyncpg pool, or PgBouncer in **transaction** mode. Disable asyncpg's statement cache
  under PgBouncer. No RDS Proxy on the RLS path until session pinning has been measured.
- **Keys and indexes:** UUIDv7 generated in the app. Postgres 16 with ltree, pg_trgm, pgvector and pgcrypto. PostGIS is added only when a module needs it.
- **TESTING-05:** apply all migrations to an empty database and to the previous release's schema snapshot, then diff. Downgrades are not supported.

## Consequences

An import-linter rule bans using `sqlalchemy` engines or connections outside `aip/platform/db`. Repositories
receive the tenant-bound connection and never create their own.
