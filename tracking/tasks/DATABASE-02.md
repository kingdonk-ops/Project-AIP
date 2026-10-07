# DATABASE-02 — Roles, with_tenant session helper and fail-closed tenant context
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python backend, no AIP reuse), [0002](../../docs/adr/0002-data-access-and-migrations.md) (roles, `with_tenant`, `set_config(..., true)`, NULLIF policy, PgBouncer), [0004](../../docs/adr/0004-repository-layout.md) (`aip/platform/db`, `db/templates/`, `migrations/versions/`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Make the tenant boundary a database property: non-owner roles, one `with_tenant` transaction helper that sets `app.tenant_id` with `set_config(..., true)`, and policies that fail closed when the setting is unset. DATABASE-01 was dropped (merged into TESTING-02); there is no AIP schema to start from.

- **depends on**:
  - DATABASE-01
- **files**:
  - apps/api/migrations/versions/<rev>_platform_roles.py (Alembic revision, raw SQL via `op.execute`, forward-only)
  - db/templates/tenant_table.sql.tpl
  - apps/api/aip/platform/db/engine.py
  - apps/api/aip/platform/db/session.py
  - apps/api/aip/platform/db/errors.py
  - apps/api/aip/platform/db/PGBOUNCER.md (compatibility note)
  - apps/api/tests/platform/db/test_session.py
  - apps/api/tests/platform/db/test_session_pgbouncer.py
- **steps**:
  - 1. In the roles revision create `aip_owner` (owns every table; used only by migrations), `aip_app` (LOGIN, NOSUPERUSER, NOBYPASSRLS, not an owner of anything), `aip_jobs` (Procrastinate tables plus the outbox publish columns, granted later by OPS-02/ARCH-05), and `aip_readonly` (SELECT for reporting, still subject to RLS). Use `DO $$ ... IF NOT EXISTS ... $$` so the revision is re-runnable on a fresh cluster. Passwords come from the environment/Secrets Manager, never the repo.
  - 2. Write `db/templates/tenant_table.sql.tpl` with placeholders `{{table}}` and `{{columns}}`: `id uuid PRIMARY KEY` (UUIDv7 generated in the app), `tenant_id uuid NOT NULL`, `created_at`/`updated_at timestamptz NOT NULL DEFAULT now()`, `deleted_at timestamptz NULL`, `ENABLE` and `FORCE ROW LEVEL SECURITY`, one policy `tenant_isolation` FOR ALL with both `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)` and the same `WITH CHECK`, an index on `(tenant_id)`, and `GRANT SELECT, INSERT, UPDATE, DELETE ... TO aip_app`, `GRANT SELECT ... TO aip_readonly`. Add a small renderer `render_template(name, **vars)` in `aip/platform/db/templates.py` that revisions call (`op.execute(render_template("tenant_table", table="...", columns="..."))`).
  - 3. In `engine.py` build one bounded `AsyncEngine` (SQLAlchemy 2.0 Core on `asyncpg`) connecting as `aip_app`. When `DB_POOL_MODE=pgbouncer`, pass `connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0}` and use `NullPool`/a small pool per ADR 0002. No other module may create an engine (import-linter contract added by ARCH-01; reference it in the PR).
  - 4. In `session.py` implement `async with with_tenant(tenant_id) as conn:` (an `asynccontextmanager` yielding an `AsyncConnection`): validate `tenant_id` is a `uuid.UUID` (or a uuid string) and raise `InvalidTenantError` before acquiring a connection; then `async with engine.begin() as conn:` and `await conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})`; yield; commit on exit, roll back on exception. Session-level `SET` is banned: add a test that greps `aip/` for `SET app.tenant_id` / `set_config(..., false)` and fails.
  - 5. Fail closed: with the setting unset or empty, the NULLIF policy compares to NULL, so SELECT sees 0 rows and INSERT/UPDATE fail `WITH CHECK` (SQLSTATE 42501).
  - 6. Write `PGBOUNCER.md`: transaction pooling only, statement cache disabled, `set_config(..., true)` is transaction-scoped so it is safe; no RDS Proxy on the RLS path until session pinning is measured (ADR 0002). Add the PgBouncer test below.
- **acceptance**:
  - `aip_app` cannot read any row without a tenant set (0 rows, never data) and cannot insert.
  - `aip_app` owns no table and has `rolbypassrls = false`; tables are owned by `aip_owner`.
  - Tenant context does not leak between pooled connections or between transactions on the same connection.
  - Nothing outside `aip/platform/db` creates a SQLAlchemy engine or connection.
- **tests**:
  - **e2e**:
    - Call an authenticated FastAPI endpoint (a fixture route using `with_tenant`) without a tenant-bearing principal. Expected: 401 and zero pool checkouts (counted via a SQLAlchemy `checkout` pool event listener).
  - **integration** (pytest + testcontainers-python, Postgres 16; table `rls_probe` created from `tenant_table.sql.tpl` as `aip_owner`, two rows seeded for tenants A and B as owner):
    - As `aip_app` with no tenant set, `SELECT count(*) FROM rls_probe`. Expected: 0 (or an error, never data).
    - As `aip_app` with no tenant set, `INSERT INTO rls_probe (id, tenant_id) VALUES (...)`. Expected: SQLSTATE 42501.
    - `with_tenant(A)` then `with_tenant(B)` on a pool of size 1 (same physical connection). Expected: B sees only B's row; after both, `current_setting('app.tenant_id', true)` on a fresh transaction is `''` or NULL.
    - `SELECT rolbypassrls FROM pg_roles WHERE rolname='aip_app'`. Expected: false. `SELECT count(*) FROM pg_tables WHERE tableowner='aip_app'`. Expected: 0.
    - PgBouncer (generic `DockerContainer` running a PgBouncer image, `POOL_MODE=transaction`) in front of Postgres; 20 parallel `with_tenant` transactions alternating A and B, each reading `rls_probe`. Expected: zero cross-tenant rows and no prepared-statement errors.
  - **unit**:
    - `with_tenant("not-a-uuid")` raises `InvalidTenantError` before any connection is acquired (engine stub asserts no checkout).
    - `render_template("tenant_table", table="x", columns="name text")` output contains `FORCE ROW LEVEL SECURITY`, `NULLIF(current_setting('app.tenant_id', true), '')::uuid` and `WITH CHECK`.
