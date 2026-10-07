# DATABASE-07 — Isolation test generator across all tables and routes

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, STACK-03, TESTING-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Generate cross-tenant and IDOR tests so new tables inherit coverage.

- **depends on**:
  - DATABASE-03
- **files**:
  - tests/db/rls-isolation.generated.spec.ts
  - tools/ci/gen-isolation-tests.ts
  - tests/db/migrations-updownup.spec.ts
- **steps**:
  - 1. Read the table catalogue from pg_catalog and the route list from the OpenAPI schema.
  - 2. For each table, seed one row per tenant A and B, then assert A's session sees only its row and cannot UPDATE or DELETE B's row by id.
  - 3. For each GET /:id route, call it as tenant A with B's id. Expected: 404.
  - 4. Fail the build if any table or route is skipped without an exception entry.
  - 5. Publish the results as a CI evidence artefact.
- **acceptance**:
  - Adding a table with no policy fails CI.
  - Every ID-addressed route is exercised for IDOR.
  - The artefact lists per-table results.
- **tests**:
  - **e2e**:
    - Run the isolation job in CI on a PR adding a new table via the template. Expected: green. Hand-write one without a policy. Expected: red.
  - **integration**:
    - With a fixture table lacking a policy, the generated test fails with 'cross-tenant read returned rows'.
    - With the real schema, all generated table tests pass.
    - Cross-tenant PATCH /assets/:id with B's id as tenant A. Expected: 404 and B's row is unchanged.
  - **unit**:
    - The generator emits one test per catalogue table (fixture of 3 tables gives 3 tests).
