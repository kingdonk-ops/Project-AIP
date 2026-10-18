# PORTAL-06 — Witness attendance: confirm or waive under the project's notice period and waiver rule

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | PORTAL-04, PROJECTS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Let a client confirm attendance at a witness point or waive it, applying the project's witness notice period and waiver rule, which are project settings (PROJECTS-04: `witness_notice_hours`, `witness_waiver_rule`; owner 2026-10-18); confirm the default values with the owner when this spec is written (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
