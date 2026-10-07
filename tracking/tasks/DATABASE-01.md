# DATABASE-01 — Audit existing AIP schema against conventions

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Produce a factual gap list so migrations target real gaps.

- **files**:
  - tools/ci/check_schema_conventions.py
  - docs/conventions/schema-conventions.md
  - docs/spec/aip-schema-gap-report.md
- **steps**:
  - 1. Write docs/conventions/schema-conventions.md covering uuid PK, tenant_id, created_at and updated_at, sync_version, deleted_at, asset_id and naming.
  - 2. Write the CI checker that queries pg_catalog for each table: tenant_id column, RLS enabled, FORCE RLS, required indexes and append-only grants.
  - 3. Read exceptions from schema_convention_exceptions.
  - 4. Run it against the current AIP migrations applied to a test database, and commit the gap report.
  - 5. Emit the JSON report as a CI artefact.
- **acceptance**:
  - The report lists every AIP table with a pass or fail for each control.
  - The checker exits 1 if any non-exempt table fails.
  - The JSON artefact is uploaded.
- **tests**:
  - **e2e**:
    - Run the checker on the full AIP schema in CI. Expected: the artefact rls_coverage.json is stored and its tables_total equals the count from information_schema.
  - **integration**:
    - Create fixture table t_ok (tenant_id, RLS and FORCE) and t_bad (no RLS). Expected: the report shows 1 pass and 1 fail, exit code 1.
    - Add t_bad to the exceptions table. Expected: exit code 0.
  - **unit**:
    - The classifier flags a table lacking tenant_id as FAIL(tenant_id).
    - A table listed in exceptions is skipped with a reason.
