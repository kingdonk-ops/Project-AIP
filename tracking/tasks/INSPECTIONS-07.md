# INSPECTIONS-07 — Eligibility banner and hard block at step sign-off

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | ELIGIBILITY-02, INSPECTIONS-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Call the eligibility check before each step sign-off, show the banner, and refuse a signer or instrument that fails it (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
