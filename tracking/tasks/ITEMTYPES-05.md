# ITEMTYPES-05 — Custom status sets mapped to neutral lifecycle states

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`item_types`](../../docs/blueprint/modules/item_types/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ITEMTYPES-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/item_types/README.md`](../../docs/blueprint/modules/item_types/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions), [0039](../../docs/adr/0039-owner-answers-item-types-witness-root-cause.md) (owner answers)

## Spec

Let each item type carry a custom status set whose values map to a fixed set of neutral lifecycle states that gates and reports rely on (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).

Owner answered [OPEN-QUESTIONS](../OPEN-QUESTIONS.md) #40 on 2026-10-30 (neutral states draft, scoped, planned, in progress, on hold, completed, cancelled, decommissioned); write the full spec from [ADR 0039](../../docs/adr/0039-owner-answers-item-types-witness-root-cause.md).
