# PORTAL-07 — External users admin: register, invite with grant builder, pending approvals (/admin/portal/users)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-03, PORTAL-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Build the internal admin page for external users: the register with a pending-approvals tab, the invite form with a grant builder (project, optional asset subtree, actions), and suspend or expire access (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
