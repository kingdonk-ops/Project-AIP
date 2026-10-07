# DATABASE-04 — Base repository helpers: concurrency, ltree, soft delete, JSONB validation

| Field | Value |
|---|---|
| Module | [`database`](../../docs/blueprint/modules/database/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/database/README.md`](../../docs/blueprint/modules/database/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Provide shared helpers so modules never hand-write conventions.

- **depends on**:
  - DATABASE-02
- **files**:
  - apps/api/src/platform/db/concurrency.ts
  - apps/api/src/platform/db/ltree.ts
  - apps/api/src/platform/db/soft-delete.ts
  - apps/api/src/platform/db/jsonb-schema.ts
- **steps**:
  - 1. concurrency: updateWithVersion(table, id, expectedVersion, patch) increments sync_version and throws ConflictError(409) carrying the current row on mismatch.
  - 2. ltree: descendants, ancestors and moveSubtree (a single UPDATE rewriting paths), with a guard against moving a node under itself.
  - 3. soft-delete: softDelete and restore, with every default query filtering deleted_at IS NULL.
  - 4. jsonb-schema: validateAttributes(typeSchema, value) using Zod built from the stored per-type JSON Schema.
  - 5. Add client_generated_id unique per tenant, with an idempotent create helper.
- **acceptance**:
  - A stale version returns 409 with the current record in the body.
  - Moving a node under its own descendant is rejected.
  - A repeated create with the same client_generated_id returns the original row.
- **tests**:
  - **e2e**:
    - Edit one asset in two browser sessions and save the second. Expected: the conflict dialog shows a field diff with Merge, Reload and Cancel.
  - **integration**:
    - Move node A.B (with 3 descendants) under A.C. Expected: all 4 paths are rewritten and the descendants count is unchanged.
    - Two concurrent updates with the same expected version. Expected: one 200 and one 409.
    - Soft delete an asset, then GET it. Expected: 404. Restore it. Expected: 200.
  - **unit**:
    - updateWithVersion with expected 3 against stored 4 throws ConflictError with current.sync_version=4.
    - moveSubtree('a.b','a.b.c') throws CycleError.
    - validateAttributes on {wall_loss_mm:'x'} against a numeric schema returns a path-specific error.
