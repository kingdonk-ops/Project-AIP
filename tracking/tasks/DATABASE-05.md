# DATABASE-05 — Append-only grants and time partitioning
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (greenfield, no AIP schema), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Alembic raw-SQL revisions, append-only template, roles), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate periodic jobs), [0004](../../docs/adr/0004-repository-layout.md)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Make evidence tables immutable to the application roles and keep monthly partitions created ahead of time. This is a greenfield schema: tables that do not exist yet get these properties from the append-only template when their module creates them.

- **depends on**:
  - DATABASE-03
- **files**:
  - db/templates/append_only_table.sql.tpl
  - apps/api/migrations/versions/<rev>_append_only_grants.py
  - apps/api/migrations/versions/<rev>_partition_functions.py
  - apps/api/aip/platform/db/partitions.py
  - apps/api/aip/platform/db/jobs.py (Procrastinate periodic task `ensure_partitions`)
  - apps/api/tests/platform/db/test_partitions.py
- **steps**:
  - 1. Write `append_only_table.sql.tpl`: the tenant template's columns and FORCE RLS policy without `deleted_at`/`updated_at`, `PARTITION BY RANGE ({{partition_column}})`, a `DEFAULT` partition, `GRANT SELECT, INSERT` to `aip_app`, and an explicit `REVOKE UPDATE, DELETE, TRUNCATE ... FROM aip_app, aip_jobs, aip_readonly`.
  - 2. In `<rev>_append_only_grants.py`, for each of `inspection_responses`, `audit_log`, `sync_operations` and `activity` that already exists on main: `REVOKE UPDATE, DELETE, TRUNCATE ... FROM aip_app, aip_jobs`. If a table exists but is not partitioned and holds rows, convert it with expand and contract (create the partitioned `<table>_p`, copy, verify count and checksum inside the revision, swap names, drop the old table in the same revision only after the check passes). Tables not yet on main are listed in the revision docstring as "must use append_only_table.sql.tpl".
  - 3. Add table `partition_settings` (global reference table: `table_name` PK, `partition_interval` `'month'` only for now, `months_ahead` default 3; allow-listed in TESTING-02 with a reason) and a `SECURITY DEFINER` function `aip_ensure_partitions(table_name text, months_ahead int)` owned by `aip_owner`, with `EXECUTE` granted only to `aip_jobs`, that creates missing monthly partitions `<table>_YYYY_MM`.
  - 4. In `partitions.py` write pure helpers `partition_name(table, d: date) -> str` and `missing_partitions(existing: set[str], today: date, months_ahead: int) -> list[str]`. In `jobs.py` register a Procrastinate periodic task (`@app.periodic(cron="17 2 * * *")`, queue `default`) that calls the function for every row in `partition_settings`, and logs at ERROR plus emits metric `db_partition_create_failed` on any failure (alerting wired by ops).
  - 5. If `inspection_current_responses` exists on main, verify it still returns the latest value per field after partitioning; otherwise add that check to the inspections task that creates the view (note it in the PR).
- **acceptance**:
  - UPDATE, DELETE and TRUNCATE on an append-only table as `aip_app` or `aip_jobs` fail with permission denied.
  - The partition for next month always exists for every table in `partition_settings`.
  - No data is lost in any conversion (row count and checksum identical).
- **tests**:
  - **e2e**:
    - If the inspections module is on main: submit an inspection response twice for the same field, then query `inspection_current_responses`. Expected: the latest value is returned and the history endpoint lists both entries. Otherwise this is covered by the integration checksum test and noted in the PR.
  - **integration** (pytest + testcontainers-python; fixture table `evidence_probe` rendered from `append_only_table.sql.tpl` on `created_at`, registered in `partition_settings`):
    - As `aip_app` inside `with_tenant`: `UPDATE evidence_probe SET ...`. Expected: SQLSTATE 42501 (permission denied). Same for `DELETE` and `TRUNCATE`.
    - Insert a row dated next month before the job runs. Expected: it lands in the DEFAULT partition; after `ensure_partitions` runs (call the task function directly), `<table>_YYYY_MM` exists for the next 3 months and a new insert for next month lands in it.
    - Seed 1,000 rows into an unpartitioned `evidence_probe_legacy`, run the expand/contract path. Expected: `count(*)` and `md5(string_agg(t::text, ',' ORDER BY id))` identical before and after.
    - As `aip_app`, `SELECT aip_ensure_partitions('evidence_probe', 3)`. Expected: permission denied (only `aip_jobs` may execute).
  - **unit**:
    - `partition_name("audit_log", date(2025, 7, 15))` returns `"audit_log_2025_07"`.
    - `missing_partitions({"audit_log_2025_07"}, date(2025, 7, 15), 2)` returns `["audit_log_2025_08", "audit_log_2025_09"]`.
