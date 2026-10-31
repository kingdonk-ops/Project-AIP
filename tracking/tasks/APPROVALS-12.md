# APPROVALS-12 — Escalation and reminders for overdue approval steps

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

Use `approval_steps.due_at` and `approval_route_templates.escalation_hours` (created unused by APPROVALS-04): a scheduled job finds overdue `pending` steps, sends reminders through notifications and emits `workflow.escalated`, marking the step `escalated` after the escalation window (tag: extend).

Stub (found by APPROVALS-04, which left these columns unused): the full spec is written before the task starts.
