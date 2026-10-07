# DATABASE-06 — Legal hold and recycle bin

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Block purge under legal hold, including asset subtree holds.

- **depends on**:
  - DATABASE-04
- **files**:
  - migrations/versions/0130_legal_holds.sql
  - apps/api/src/modules/records/legal-hold.service.ts
  - apps/api/src/modules/records/recycle-bin.controller.ts
  - apps/api/src/modules/records/purge.job.ts
- **steps**:
  - 1. Migration for legal_holds (scope_type record|asset|project, scope_id, reason, matter_ref, placed_by, placed_at, released_at).
  - 2. isHeld(record) checks the record, then the project, then ancestors via ltree path.
  - 3. Recycle bin endpoints: list, restore and purge. Purge returns 423 when held.
  - 4. The purge job skips held records and logs the skip.
  - 5. Emit events for hold placed and hold released.
- **acceptance**:
  - A hold on an asset also protects its descendants.
  - Release re-enables purge.
  - Purge of a held record is refused, with the hold id returned.
- **tests**:
  - **e2e**:
    - In the Recycle bin page, select a held record and click Purge. Expected: the button is blocked with a hold banner. Place and release a hold in /admin/legal-holds and confirm the state change.
  - **integration**:
    - Hold asset A.B and soft-delete A.B.C. Purge A.B.C. Expected: 423.
    - Release the hold and purge. Expected: 204.
    - Run the purge job with 3 deleted records (1 held). Expected: 2 purged and 1 skipped with a log entry.
  - **unit**:
    - isHeld returns true for a child asset whose ancestor has an active asset hold, false after release.
