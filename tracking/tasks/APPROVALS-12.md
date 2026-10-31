# APPROVALS-12 — Delegation of approval steps with a date range and audit visibility

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P1 |
| Size | M |
| Depends on | APPROVALS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0035](../../docs/adr/0035-transition-service-implementation.md), [0040](../../docs/adr/0040-approval-routes-implementation.md)

## Spec

Let an approver delegate their route steps to another user for a date range and scope; a delegate's decision records `on_behalf_of` in the decision history, and the instance timeline shows who acted for whom (tag: extend). Coordinate with the ACCESS-08 team delegation guard.

Stub (found by APPROVALS-04, which left these columns unused): the full spec is written before the task starts.
