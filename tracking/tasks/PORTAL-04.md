# PORTAL-04 — Client review and hold-point release in the portal with sign-off assurance

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-05, PORTAL-03 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions)

## Spec

Let a client with a grant on the project review and sign an inspection awaiting client review and release a hold point from the portal, through `ApprovalsApi.transition` with the ADR 0010 sign-off check (passkey on their phone, or phone confirmation), never through admin routes (tag: extend).

Stub: full spec is written when its dependencies are merged (PLAN-R1 pass A).
