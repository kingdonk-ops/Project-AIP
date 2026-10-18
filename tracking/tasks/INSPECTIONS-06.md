# INSPECTIONS-06 — Hold-point scenarios on CUI data (split from TESTING-06)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | INSPECTIONS-03, SCOPEWORK-03, TESTING-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Golden hold-point scenarios on synthetic CUI data: a hold blocks its downstream task until released, and a witness point records a waiver (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
