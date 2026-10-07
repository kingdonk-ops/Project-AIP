# TESTING-02 — Schema guard: tenant_id and RLS on every table

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | TESTING-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

CI fails when any table lacks tenant_id, ENABLE and FORCE RLS, or a policy.

- **depends on**:
  - TESTING-01
- **files**:
  - backend/tests/tenancy/test_schema_guard.py
  - backend/tests/tenancy/schema_guard_allowlist.yaml
- **steps**:
  - 1. Query information_schema and pg_class for all public tables, excluding alembic_version and allow-listed global reference tables.
  - 2. Assert a tenant_id uuid column exists.
  - 3. Assert relrowsecurity and relforcerowsecurity are both true.
  - 4. Assert at least one policy exists in pg_policies.
  - 5. Require each allow-list entry to carry a written reason string.
  - 6. Emit a failure message that names each offending table.
- **acceptance**:
  - A new table without RLS makes the test fail and name the table.
  - The allow-list is reviewed via CODEOWNERS.
- **tests**:
  - **e2e**:
    - A PR adding a migration with an unprotected table is blocked by the CI check.
  - **integration**:
    - Create a temporary table t_bad(id uuid) in the test DB: the guard reports 't_bad' missing tenant_id.
    - Create t_ok with tenant_id, RLS and FORCE: the guard passes it.
    - Against the real migrated schema, the guard reports 0 violations, or lists the AIP tables to be fixed (backlog output).
  - **unit**:
    - Allow-list parser rejects an entry with an empty reason.
