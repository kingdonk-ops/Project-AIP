# ELIGIBILITY-06 — Override request queue page for the quality manager

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`eligibility`](../../docs/blueprint/modules/eligibility/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | DESIGN-03, ELIGIBILITY-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/eligibility/README.md`](../../docs/blueprint/modules/eligibility/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Build the override request queue for the quality manager: pending requests with reason and expiry, approve or reject through the ELIGIBILITY-03 API (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
