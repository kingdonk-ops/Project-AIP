# ADR 0040: Approval routes: how the APPROVALS-04 spec meets the transition engine

- **Status:** accepted
- **Date:** 2026-10-31
- **Affects:** approvals, access; APPROVALS-04, APPROVALS-06, INSPECTIONS-05

## Context

APPROVALS-04 adds approval routes (ordered user, role or team approver steps, serial or parallel)
to the workflow engine of APPROVALS-01/02. Its spec was written for the NestJS stack and before
ADR 0027 (permission verbs) and ADR 0035 (transition service). Converting it to Python (ADR 0001)
left choices the spec does not settle, and the existing workflow and inspection-preset behaviour
must not change.

## Decision

1. **One engine.** A finished route takes its template's `on_approved_action` or
   `on_rejected_action` through the transition service's own steps (pinned definition, graph
   check, guard, sign-off assurance, hash-chained row, `workflow.transitioned`) in the same
   transaction as the last decision. The route's decisions stand in for the transition's
   `requiredPermission`. Instances without a route behave exactly as before.
2. **The decide permission is `approvals.approve`**, not the spec's `approvals.decide`. Under
   ADR 0027 the verb `approve` is granted at the `approve` level, including the sign-off-only
   Client Reviewer role that INSPECTIONS-05's client review step needs; `decide` is no verb and
   would be admin-only. Eligibility (user, role or team) is checked on top, at decision time.
3. **Role approvers are role ids** (the data model's `approver_ref uuid`), resolved to a code
   through `access/api.py` (`role_code_for_id`) and checked with `has_role` on the instance's
   project or tenant-wide. Team approvers need a live membership of a live team that is
   tenant-level or on the instance's project (`teams_for_user`). Role and team approvers must
   exist when a template is created (422 `UNKNOWN_APPROVER`); user approvers are not checked
   there, because only that user can ever decide the step.
4. **A critical completion transition** checks the last decider's sign-off assurance:
   `step_up_required` is 401 `STEP_UP_REQUIRED` and nothing is written; `countersign_required`
   is 403 `COUNTERSIGN_ASSURANCE_REQUIRED`, because a route decision is never left pending a
   countersign.
5. **History.** Every step decision appends a hash-chained `workflow_decision_history` row with
   its `step_id`. A decision that finishes the route is the transition row itself; any other is a
   non-moving row (`from_state == to_state`, action `approve_step` or `reject_step`). A serial
   two-step route after a submit therefore has three rows.
6. **The route owns its two actions.** While a route runs (`current_step_id` is set),
   `POST /transition` refuses them (409 `ROUTE_PENDING`, reason key `approvals.route.pending`
   in `availableTransitions`). Any other transition that takes effect cancels the route: its open
   steps become `skipped`. A route starts only when both actions are legal from the current state
   (422 `ROUTE_ACTION_INVALID`).
7. **Rounds.** A route can follow a finished or cancelled one (rework, resubmit). Steps carry a
   `route_round`; `GET /instances/{id}/steps` and decisions use the latest round. Steps of later
   groups wait as `waiting`, a status the data model did not list.
8. **Separation of duties.** The route's submitter is the actor of the instance's last applied
   decision when the route starts (the person who submitted), else whoever started the route. They
   cannot decide any step unless the template sets `allow_self_approval` (403
   `SELF_APPROVAL_FORBIDDEN`).
9. **Errors** follow ADR 0035: a reject without a comment is 422 `COMMENT_REQUIRED` (the spec
   said 400); a waiting step or an ineligible actor is 403 `NOT_CURRENT_APPROVER`; a decided or
   skipped step is 409 `STEP_NOT_PENDING`; another tenant's instance or template is 404.
10. **Unused columns.** `conditions`, `threshold_bands`, `escalation_hours` and
    `required_discipline_id` are created but unused. Threshold bands, escalation with reminders,
    and delegation are the stubs APPROVALS-10, APPROVALS-11 and APPROVALS-12.
11. **The Playwright API journey is carried to APPROVALS-06** (as ADR 0035 §9 did for
    APPROVALS-02): the deployed `demo` seed has no route template or second approver fixture. The
    integration tests run the same HTTP journey in-process.

## Consequences

- APPROVALS-06 builds its inbox on `ApprovalsApi.pending_steps`, which filters candidate steps by
  eligibility and `approvals.view` in Python; an inbox at scale may need a SQL-side role filter.
- INSPECTIONS-05 can start a client review route whose `on_approved_action` is the critical
  `client_approve` transition; the client approver must be stepped up.
- `approval.requested`, `approval.approved`, `approval.rejected` and `approval.completed` v1 are
  released event schemas.
