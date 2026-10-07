# TESTING-01 — Testcontainers Postgres fixture with non-owner RLS role

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Every integration test runs against real PostGIS as a non-owner, non-BYPASSRLS role with a transaction-scoped tenant setting that fails closed.

- **files**:
  - backend/tests/conftest.py
  - backend/tests/tenancy/test_rls_fixture.py
  - backend/app/platform/db/tenant_session.py
- **steps**:
  - 1. Add a session-scoped PostGIS Testcontainer fixture that runs Alembic upgrade head as the owner role.
  - 2. Create role aip_app (NOLOGIN to LOGIN, NOSUPERUSER, NOBYPASSRLS) and grant table privileges.
  - 3. Add an async session factory that connects as aip_app and runs SET LOCAL app.tenant_id = :t inside each transaction.
  - 4. Make RLS policies read current_setting('app.tenant_id', true) so an unset value returns zero rows and rejects writes.
  - 5. Add fixtures tenant_a and tenant_b plus a helper as_tenant(tenant_id).
  - 6. Document the fixtures in the test README.
- **acceptance**:
  - Tests never connect as the owner role.
  - A query with no tenant set returns 0 rows and an insert fails.
  - The tenant setting does not leak between transactions on a pooled connection.
- **tests**:
  - **e2e**:
    - CI job 'integration' starts the container and runs the whole suite green in under 10 minutes.
  - **integration**:
    - Insert an inspection as tenant A, then select as tenant B: 0 rows.
    - Select with app.tenant_id unset: 0 rows, no exception.
    - Run 50 concurrent transactions alternating A and B on a pool of size 2: every transaction sees only its own rows.
    - SELECT rolbypassrls FROM pg_roles WHERE rolname='aip_app' returns false.
  - **unit**:
    - as_tenant(None) raises TenantNotSetError before any SQL runs.
    - Session factory emits SET LOCAL once per transaction, checked via SQL log capture.
