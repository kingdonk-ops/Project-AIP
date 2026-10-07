# ADR 0002: Kysely for data access; forward-only SQL migrations via node-pg-migrate

- **Status:** accepted (supersedes the decision text "Keep Alembic raw SQL with templates"; owner to confirm)
- **Date:** 2026-10-07
- **Affects:** database and every module with tables; STACK-01, DATABASE-*, TESTING-01, TESTING-05, OPS-01

## Context

The decision "Keep Alembic raw SQL with templates" keeps the right *intent*: hand-written, reviewed,
forward-only SQL from templates. But it names a Python tool. The system leans heavily on Postgres features:
FORCE RLS with per-transaction `SET LOCAL`, ltree, pgvector, FTS, partitions and append-only grants.
See docs/reviews/05-stack-data.md and 06-stack-typescript.md.

## Decision

- **Query layer: Kysely** over `pg`. It's SQL-first and typed, and handles ltree, pgvector and raw
  fragments cleanly. Prisma is rejected (weak RLS / `SET LOCAL` story). Drizzle is the fallback; it sits
  behind the repository base either way.
- **Migrations:** plain `.sql` files in `db/migrations/`, forward-only, run by `node-pg-migrate` (SQL mode) as
  the migrator role. New migrations start from `db/templates/` (tenant table, append-only table). Kysely types
  are generated from the schema (`kysely-codegen`) and drift-checked in CI.
- **Tenant context:** every request runs inside `withTenant(ctx, fn)`, which opens a transaction and calls
  `select set_config('app.tenant_id', $1, true)`. Session-level `SET` is forbidden. Policies use
  `NULLIF(current_setting('app.tenant_id', true), '')::uuid` with `USING` and `WITH CHECK`, so an
  unset context fails closed.
- **Roles:** `aip_owner` (migrations), `aip_app` (no BYPASSRLS, not owner), `aip_dispatcher` (outbox publish
  columns only), `aip_readonly` (reporting).
- **Pooling:** a bounded direct pool or PgBouncer in **transaction** mode. No RDS Proxy on the RLS path until
  pinning is measured. The migrator and dispatcher use direct connections.
- **Keys:** UUIDv7, generated in the app.
- **TESTING-05:** replace "up-down-up" with "apply on an empty DB and on the previous release's schema
  snapshot, then diff".
- **Test image:** Postgres 16 with ltree, pg_trgm and pgvector. Add PostGIS only when a module needs it.

## Consequences

No Python in the main build. A lint rule bans importing `pg` or Kysely outside `apps/api/src/platform/db`.
