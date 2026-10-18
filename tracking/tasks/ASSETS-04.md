# ASSETS-04 — Bulk add (name pattern, start number, repeats) and sibling reorder

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`assets`](../../docs/blueprint/modules/assets/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | ASSETS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/assets/README.md`](../../docs/blueprint/modules/assets/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add bulk add under a node (name pattern with ###, start number, up to 100 repeats) and sibling reorder by sort order (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
