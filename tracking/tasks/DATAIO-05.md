# DATAIO-05 — Update-by-key mode for bulk edits of existing records

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`data_io`](../../docs/blueprint/modules/data_io/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | DATAIO-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/data_io/README.md`](../../docs/blueprint/modules/data_io/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add an update-by-key import mode for bulk edits of existing records, with the same dry run and batch rollback (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
