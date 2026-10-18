# FORMS-07 — Calculated fields: a forms-only arithmetic extension to the shared evaluator (DFT average, corrosion rate)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | FORMS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/forms/README.md`](../../docs/blueprint/modules/forms/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Add calculated fields: a forms-only arithmetic extension (`+ - * / min max round`) layered on the approvals guard allow-list, in the Python and TypeScript evaluators with shared golden vectors, cycle-checked by the FORMS-01 lint, for values such as a DFT average or a corrosion rate (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
