# DATABASE-02 — Roles, session helper and fail-closed tenant context

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Make the tenant boundary a database property with non-owner roles and SET LOCAL per transaction.

- **depends on**:
  - DATABASE-01
- **files**:
  - migrations/roles.sql
  - migrations/templates/new_table.sql.tpl
  - apps/api/src/platform/db/session.ts
  - apps/api/src/platform/db/session.spec.ts
- **steps**:
  - 1. In roles.sql create migrator (owner), app (NOLOGIN inheritance, no BYPASSRLS, no ownership), readonly and dispatcher roles.
  - 2. Write the new_table.sql.tpl template with tenant_id, FORCE RLS, the policy using current_setting('app.tenant_id', true)::uuid, indexes and grants.
  - 3. Implement withTenantTx(fn): begin, SELECT set_config('app.tenant_id', $1, true), run fn, commit.
  - 4. Make the policy fail closed: when the setting is unset or empty, no rows are visible and writes are rejected.
  - 5. Provide a PgBouncer or RDS Proxy compatibility note and a test that runs in transaction pooling mode.
- **acceptance**:
  - The app role cannot read any rows without a tenant set.
  - The app role is not a table owner and has no BYPASSRLS.
  - Tenant context does not leak between pooled connections.
- **tests**:
  - **e2e**:
    - Call an authenticated endpoint without a tenant claim. Expected: 401 and no database query is executed.
  - **integration**:
    - Testcontainers: as app with no tenant set, SELECT count(*) FROM assets. Expected: 0 (or an error, never data).
    - Run withTenantTx for A then B on the same connection. Expected: B sees only B's rows.
    - SELECT rolbypassrls FROM pg_roles WHERE rolname='app'. Expected: false.
    - Run with PgBouncer in transaction mode and 20 parallel transactions across 2 tenants. Expected: zero cross-tenant rows.
  - **unit**:
    - withTenantTx rejects a non-uuid tenant id with InvalidTenantError before touching the database.
