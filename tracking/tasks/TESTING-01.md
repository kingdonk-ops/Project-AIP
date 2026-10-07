# TESTING-01 — Testcontainers Postgres fixture with non-owner RLS role
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (pytest / testcontainers-python), [0002](../../docs/adr/0002-data-access-and-migrations.md) (roles, `with_tenant`, NULLIF fail-closed policy), [0004](../../docs/adr/0004-repository-layout.md) (`apps/api/tests/`, `apps/api/migrations/`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Every backend integration test runs against real Postgres 16 (ltree, pg_trgm, pgvector, pgcrypto) as `aip_app` — a non-owner, non-BYPASSRLS role — with a transaction-scoped tenant setting that fails closed. Never mock the database.

- **files**:
  - apps/api/tests/conftest.py
  - apps/api/tests/fixtures/postgres.py
  - apps/api/tests/fixtures/bootstrap_roles.sql
  - apps/api/tests/fixtures/rls_probe.sql
  - apps/api/tests/tenancy/test_rls_fixture.py
  - apps/api/tests/README.md
  - apps/api/aip/platform/db/session.py (only if DATABASE-02 has not merged: a minimal `with_tenant`; DATABASE-02 owns its final form, so coordinate rather than duplicate)
- **steps**:
  - 1. Add a session-scoped `PostgresContainer` fixture (testcontainers-python, image `pgvector/pgvector:pg16`), with `bootstrap_roles.sql` creating `aip_owner` and `aip_app` (`LOGIN NOSUPERUSER NOBYPASSRLS`) guarded by `IF NOT EXISTS`, so it is a no-op once DATABASE-02's roles revision exists. Run `alembic upgrade head` (via `alembic.command.upgrade` with `apps/api/migrations`) as `aip_owner`.
  - 2. Grant `aip_app` table privileges only through migrations/templates; the fixture never grants extra rights. Create the test-only table `rls_probe` from `db/templates/tenant_table.sql.tpl` (or `rls_probe.sql` with the same policy if the template is not yet on main).
  - 3. Add an `app_engine` fixture: an async SQLAlchemy engine on `asyncpg` that connects as `aip_app`, and a `db` fixture yielding `with_tenant`, which runs `select set_config('app.tenant_id', :t, true)` once at the start of each transaction.
  - 4. Policies read `NULLIF(current_setting('app.tenant_id', true), '')::uuid` in both `USING` and `WITH CHECK`, so an unset value returns zero rows and rejects writes.
  - 5. Add fixtures `tenant_a` and `tenant_b` (fixed UUIDv7 values) and the helper `as_tenant(tenant_id)` (alias of `with_tenant` that raises `TenantNotSetError` on `None`). Provide `owner_conn` only for seeding, marked so a test using it for assertions fails review (fixture name `owner_conn_for_seeding_only`).
  - 6. Add the pytest marker `integration`, `pytest-asyncio` in auto mode, and document fixtures and usage in `apps/api/tests/README.md`.
- **acceptance**:
  - Tests never assert through the owner role; `aip_app` is the only role used by code under test.
  - A query with no tenant set returns 0 rows and an insert fails.
  - The tenant setting does not leak between transactions on a pooled connection.
- **tests**:
  - **e2e**:
    - CI job `integration` (`uv run pytest -m integration` in `apps/api`) starts the container and runs the whole suite green in under 10 minutes.
  - **integration**:
    - Insert a `rls_probe` row as tenant A, then select as tenant B. Expected: 0 rows.
    - Select with `app.tenant_id` unset. Expected: 0 rows, no exception. Insert with it unset. Expected: SQLSTATE 42501.
    - 50 concurrent transactions alternating A and B on a pool of size 2 (`pool_size=2, max_overflow=0`). Expected: every transaction sees only its own tenant's rows.
    - `SELECT rolbypassrls FROM pg_roles WHERE rolname='aip_app'`. Expected: false.
  - **unit**:
    - `as_tenant(None)` raises `TenantNotSetError` before any SQL runs.
    - `with_tenant` emits `set_config('app.tenant_id', ..., true)` exactly once per transaction, checked by capturing statements with a SQLAlchemy `before_cursor_execute` listener.
