# DATABASE-09 — Partition maintenance works for append-only tables with a foreign key

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DATABASE-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (forward-only raw-SQL revisions, append-only template, roles), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (the `ensure_partitions` periodic job)

## Spec

Found while building INSPECTIONS-02: `aip_ensure_partitions` (DATABASE-05) fails for an append-only
table that has a foreign key once rows sit in its `<table>_default` partition, which happens in
production before the job first runs. It moves the rows into the new `<table>_YYYY_MM` table, then
`ATTACH PARTITION` validates the cloned foreign key in one bulk query run as `aip_owner` with no
`app.tenant_id`. FORCE RLS on the referenced table hides every parent row, so the attach raises a
foreign-key violation. `workflow_definition_audit` (`fk_workflow_definition_audit_definition`)
already hits it: `PartitionMaintenanceError: partitions not ensured for: workflow_definition_audit`.
INSPECTIONS-02 left the FK off `inspection_responses` to avoid it.

- **files**:
  - apps/api/migrations/versions/<rev>_partition_fk_attach.py
  - apps/api/tests/platform/db/test_partitions.py
- **steps**:
  - 1. New forward-only revision replacing `aip_ensure_partitions`: rows for the month leave the
       default partition into a temporary staging table, the empty partition is attached (nothing
       to validate), and the rows are inserted into the attached partition. Each insert is checked
       by the per-row foreign-key trigger, which Postgres runs as the referenced table's owner with
       FORCE RLS lifted for that lookup only, so it sees the parent row whatever its tenant.
  - 2. Keep the DATABASE-05 contract: SECURITY DEFINER owned by `aip_owner`, fixed `search_path`,
       only tables listed in `partition_settings`, `EXECUTE` for `aip_jobs` only, a `# contract:`
       comment. No runtime role gains BYPASSRLS and no table's FORCE RLS is switched off.
- **acceptance**:
  - `ensure_all_partitions` creates the partitions of an append-only table whose foreign key
    points at a FORCE-RLS table, with rows already in its default partition, and moves the rows.
  - `workflow_definition_audit` with a row in its default partition gets its partitions.
  - The new partition carries the cloned foreign key and the referenced table keeps FORCE RLS.
- **tests**:
  - **integration**:
    - probe append-only table with a FK to a FORCE-RLS parent, a row in the default partition →
      `ensure_all_partitions` creates the months, the row is in its month and still joins its parent
    - workflow definition plus a next-month `workflow_definition_audit` row → partitions created,
      no `PartitionMaintenanceError`
