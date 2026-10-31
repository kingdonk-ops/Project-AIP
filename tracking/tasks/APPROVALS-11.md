# APPROVALS-11 — Approval route threshold bands and authority matrix

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P1 |
| Size | S |
| Depends on | APPROVALS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0035](../../docs/adr/0035-transition-service-implementation.md), [0040](../../docs/adr/0040-approval-routes-implementation.md)

## Spec

Choose a route's steps by the record's value: use `approval_route_templates.threshold_bands` (created unused by APPROVALS-04) and an authority matrix (role, entity, limit, currency) so a record's `record_value` picks the band, and the band adds or replaces approver steps (tag: extend).

Stub (found by APPROVALS-04, which left these columns unused): the full spec is written before the task starts.
