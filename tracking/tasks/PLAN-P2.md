# PLAN-P2 — Generate P2 task files once R1 passes its midpoint

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions), [PLAN-R1](PLAN-R1.md) (the process this repeats)

## Spec

Generate P2 task files once R1 passes its midpoint (INSPECTIONS-03 done), following the same just-in-time process as PLAN-R1: gate on the P2 modules' open questions, pass A slice plan, pass B full specs for the first three rows, and rewrite the rows parked in "Later (P2+)" (TENANCY-04, TENANCY-09, TESTING-07) per ADR 0001 (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
