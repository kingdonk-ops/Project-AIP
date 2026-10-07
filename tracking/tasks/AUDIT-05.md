# AUDIT-05 — Legal hold + recycle bin (replaces DATABASE-06)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`audit`](../../docs/blueprint/modules/audit/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | AUDIT-01, DATABASE-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/audit/README.md`](../../docs/blueprint/modules/audit/README.md)
3. ADRs: 0002 (migrations, RLS, roles), 0006 (legal hold always wins over crypto-shred), 0003 (jobs)
4. Only if the step needs it: the `legal_holds`, `legal_hold_events` and `recycle_purge_schedule` tables in [`data-model.md`](../../docs/blueprint/modules/audit/data-model.md); the soft-delete and ltree helpers from DATABASE-04 (`apps/api/src/platform/db`)

## Spec

Make deletion defensible. Soft-deleted records enter a recycle bin with a purge date. Legal holds scoped to a record, project or asset subtree block purge (and later crypto-shred). Every hold change is logged append-only. The owning module performs the actual purge or restore through handlers it registers, because audit never touches other modules' tables.

- **files**:
  - db/migrations/<timestamp>_legal_holds_recycle.sql
  - apps/api/src/modules/audit/holds.service.ts
  - apps/api/src/modules/audit/holds.controller.ts
  - apps/api/src/modules/audit/recycle.service.ts
  - apps/api/src/modules/audit/recycle.controller.ts
  - apps/api/src/modules/audit/recycle-registry.ts
  - apps/api/src/modules/audit/jobs/purge.job.ts
  - apps/api/src/modules/audit/api.ts
  - apps/api/src/modules/audit/tests/
- **steps**:
  - 1. Write one migration with three tables. `legal_holds` has id, tenant_id, name, reason, matter_ref, scope_type (`record|project|asset_subtree`), record_table, record_id, project_id, asset_path ltree, status (`active|released`), placed_by, placed_at, released_by, released_at, created_at and updated_at. A CHECK keeps the scope columns consistent with scope_type. aip_app may UPDATE only the status, released_by, released_at and updated_at columns (column-level GRANT), and DELETE is revoked. `legal_hold_events` is append-only: id, tenant_id, hold_id, action (`placed|amended|released`), actor_id, note and created_at. `recycle_purge_schedule` has id, tenant_id, record_table, record_id, project_id, asset_path, deleted_by, deleted_at, purge_after, restored_at, purged_at, created_at and updated_at, with unique (tenant_id, record_table, record_id) WHERE purged_at IS NULL AND restored_at IS NULL, and an index on purge_after WHERE purged_at IS NULL AND restored_at IS NULL. All three tables get FORCE RLS.
  - 2. In recycle-registry.ts, add `registerRecycleHandler(recordTable, {restore(tx, id), purge(tx, id), describe(tx, ids)})`, which owning modules call from their module init. Expose it, plus `AuditApi.registerSoftDelete(tx, {recordTable, recordId, projectId?, assetPath?})`, from api.ts. Modules call `registerSoftDelete` in the same transaction as DATABASE-04's `softDelete`. purge_after = deleted_at + the `audit.recycle.retention_days` setting (default 30). Retention overrides from project settings may lengthen it but never shorten it below the tenant value.
  - 3. In holds.service.ts, `isHeld(tx, {recordTable, recordId, projectId?, assetPath?})` returns the first active hold that matches: an exact record, the same project, or an `asset_path <@ hold.asset_path` (ancestor subtree). Place, amend and release write a `legal_hold_events` row in the same transaction and emit `legal_hold.placed` / `legal_hold.released`. A hold can be released only by a user other than the one who placed it, or by one holding `audit.legal_hold.override`.
  - 4. Endpoints: GET/POST `/api/v1/audit/legal-holds`, POST `/api/v1/audit/legal-holds/:id/release` (requires a note) and GET `/api/v1/audit/legal-holds/:id/events` (permission `audit.legal_hold.manage`). GET `/api/v1/audit/recycle-bin` (days remaining, held flag with hold id, describe() labels; `audit.recycle.view`). POST `/api/v1/audit/recycle-bin/:id/restore` (`audit.recycle.restore`), which calls the module's restore handler and sets restored_at. POST `/api/v1/audit/recycle-bin/:id/purge` (`audit.recycle.purge`), which returns 423 `LEGAL_HOLD` with `{holdId}` when held; otherwise it calls the purge handler, sets purged_at and emits `recycle.purged`.
  - 5. In purge.job.ts, register a daily `audit.purge` job with OPS-02. Per tenant, it selects due rows, re-checks `isHeld` for each inside the same transaction as the purge (to avoid a race with a new hold), skips held rows with a structured log `{recordTable, recordId, holdId}`, and purges the rest through their handlers. A missing handler is an error for that row only and stays visible in the job result.
  - 6. Export `AuditApi.isHeld` so TENANCY-07 (crypto-shred) and other purge paths can check holds. Mark DATABASE-06 as replaced by this task in the PR description (the board already notes it). Pages for holds and the recycle bin are a stub follow-up.
- **acceptance**:
  - A hold on asset subtree `site1.unitA` protects a soft-deleted record at `site1.unitA.pipe7`, and a release re-enables purge.
  - Purging a held record returns 423 with the hold id. The purge job never purges a held record, even when a hold is placed between selection and purge.
  - Every hold change has a matching `legal_hold_events` row. A hold row cannot be deleted, and its scope cannot be edited.
  - Audit code never reads or writes another module's tables; it only uses the registered handlers.
- **tests**:
  - **unit**:
    - isHeld with an active hold at `site1.unitA` and a record at `site1.unitA.pipe7` returns that hold. After release it returns null. A record at `site1.unitB` returns null.
    - purge_after for deleted_at `2026-10-01` with retention 30 is `2026-10-31`. A project override of 10 days with a tenant value of 30 still gives 30.
    - Release by the user who placed the hold, without the override permission, throws `SeparationOfDutiesError`.
  - **integration** (Testcontainers, with a fixture module table `widgets` registering handlers):
    - Soft-delete widget W1 at `site1.unitA.pipe7` and hold `site1.unitA`, then POST purge. Expected: 423 `{holdId}`. Release, then purge. Expected: 200, the widgets row is hard-deleted by the handler, purged_at is set, and one `recycle.purged` event exists.
    - Purge job with 3 due records, one of them held. Expected: 2 purged and 1 skipped with a log entry containing the hold id.
    - A hold is placed after the job selected the rows but before the purge (inject a hook). Expected: that record is skipped.
    - As aip_app: `UPDATE legal_holds SET asset_path='x'`. Expected: permission denied. `DELETE FROM legal_hold_events`. Expected: permission denied.
    - Tenant B lists the recycle bin. Expected: none of tenant A's rows.
    - Restore W1 before purge. Expected: the handler restores it (deleted_at null), restored_at is set, and it leaves the bin.
  - **e2e**:
    - Through the API as the kaefer-demo admin: soft-delete a fixture record, place a project hold, and try to purge (expected 423). Then a second admin releases the hold with a note and the purge succeeds. GET `/legal-holds/:id/events` shows `placed` and `released` with both actors.
