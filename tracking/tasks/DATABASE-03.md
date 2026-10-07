# DATABASE-03 — tenant_id backfill and RLS on all existing tables

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02, PLAN-R1, TENANCY-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Bring every AIP table under tenant RLS via forward-only raw-SQL migrations.

- **depends on**:
  - DATABASE-02
  - TENANCY-01
- **files**:
  - migrations/versions/0110_tenant_id_backfill_expand.sql
  - migrations/versions/0111_tenant_id_backfill_enforce.sql
  - migrations/versions/0112_rls_force.sql
- **steps**:
  - 1. Expand: add nullable tenant_id to every table the gap report flags. Derive the value from the organisation chain (assets -> sites -> projects -> organisations -> tenant).
  - 2. Backfill in batches, with a verification query that must report 0 null rows.
  - 3. Enforce: SET NOT NULL, add the foreign key and an index (tenant_id, id).
  - 4. Create policies and FORCE RLS using the template helper.
  - 5. Add the up-down-up test and run it on a snapshot-sized dataset.
- **acceptance**:
  - Zero tables are left without tenant_id and FORCE RLS, except the documented exceptions.
  - Row counts before and after the backfill are identical.
  - Migrations are repeatable up-down-up.
- **tests**:
  - **e2e**:
    - Log in as a Kaefer user and open the asset tree. Expected: the same asset count as before the migration.
  - **integration**:
    - Load AIP seed data (2 orgs, 5 assets each), migrate. Expected: every row has a non-null tenant_id and counts are unchanged.
    - Run the checker. Expected: tables_missing_controls = 0.
    - Run migrate up, down, up. Expected: no errors and an identical schema dump.
  - **unit**:
    - The SQL generator helper emits CREATE POLICY ... USING (tenant_id = current_setting('app.tenant_id', true)::uuid) for the table name given.
