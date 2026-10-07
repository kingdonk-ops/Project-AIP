# TESTING-02 — Schema guard: tenant_id, FORCE RLS and a fail-closed policy on every table
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DATABASE-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (no AIP schema; this task absorbs the dropped DATABASE-01), [0002](../../docs/adr/0002-data-access-and-migrations.md) (FORCE RLS, NULLIF policy with USING and WITH CHECK), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate tables), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder; the "Platform tables" line of the database README (`schema_convention_exceptions`)

## Spec

CI fails when any table in the migrated schema lacks `tenant_id`, `ENABLE` and `FORCE ROW LEVEL SECURITY`, or a fail-closed tenant policy. This replaces DATABASE-01 (which audited the old AIP schema): the guard reads `pg_catalog` directly and runs against the greenfield schema after `alembic upgrade head`.

- **depends on**:
  - TESTING-01
- **files**:
  - apps/api/aip/platform/db/schema_guard.py (pure inspection function, reused later by the `/admin/platform/schema-coverage` page)
  - apps/api/tests/schema/test_schema_guard.py
  - apps/api/tests/schema/schema_guard_allowlist.yaml
  - .github/CODEOWNERS (add the allow-list path)
- **steps**:
  - 1. `inspect_schema(conn) -> list[Violation]` queries `pg_class` joined to `pg_namespace` for `relkind IN ('r','p')` in schema `public` (partitions are checked through their parent: skip `relispartition`), excluding `alembic_version` and allow-listed tables.
  - 2. Assert a `tenant_id` column of type `uuid` and `NOT NULL` exists (`pg_attribute` + `format_type`).
  - 3. Assert `relrowsecurity` and `relforcerowsecurity` are both true.
  - 4. Assert at least one policy in `pg_policy` applies to all commands (`polcmd = '*'`) with both `polqual` and `polwithcheck` set, and that `pg_get_expr(polqual, polrelid)` references `current_setting('app.tenant_id'`.
  - 5. Allow-list YAML entries are `{table, reason, checks_skipped}`; an entry without a non-empty `reason` is rejected. Seed it with the known global tables, each with a reason: `deployment_regions` (global reference), `tenants` (`id` is the tenant id; policy is `id = app.tenant_id`, checked by a dedicated rule), `login_directory` (pre-login tenant resolution, ADR 0005), `partition_settings` (global settings), and Procrastinate's `procrastinate_*` tables (queue internals; payloads carry `tenant_id`, ADR 0003).
  - 6. The failure message names every offending table and the check it failed, one per line, for example `t_bad: missing tenant_id uuid NOT NULL`.
- **acceptance**:
  - A new table without RLS makes the test fail and names the table.
  - The allow-list is owned via CODEOWNERS, and every entry carries a reason.
  - The real migrated schema has 0 violations.
- **tests**:
  - **e2e**:
    - A PR adding an Alembic revision that creates an unprotected table is blocked by the required CI check `integration`.
  - **integration** (TESTING-01 fixtures; scratch tables created as the owner inside a rolled-back transaction):
    - Create `t_bad(id uuid)`. Expected: the guard reports `t_bad` missing `tenant_id`, RLS, FORCE RLS and policy.
    - Create `t_nocheck` with `tenant_id`, RLS, FORCE and a policy with `USING` but no `WITH CHECK`. Expected: reported as missing `WITH CHECK`.
    - Create `t_ok` from `db/templates/tenant_table.sql.tpl`. Expected: no violations.
    - Against the real schema after `alembic upgrade head`. Expected: 0 violations.
  - **unit**:
    - The allow-list parser rejects `{table: x, reason: ""}` with `AllowlistError` naming `x`.
    - Violation formatting for two tables produces two lines sorted by table name.
