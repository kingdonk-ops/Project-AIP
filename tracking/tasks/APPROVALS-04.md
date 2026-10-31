# APPROVALS-04 — Approval routes: sequential/parallel steps, user/role/team approvers

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: converted to the Python backend per ADR 0001 (2026-10-31) -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-04, APPROVALS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (stack), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Alembic raw SQL), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox events), [0027](../../docs/adr/0027-default-role-permission-expansion.md) (verbs and default roles), [0035](../../docs/adr/0035-transition-service-implementation.md) (transition service; 422 validation, 401 step-up, permission checks on the instance's project)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/approvals/data-model.md) (`approval_route_templates`, `approval_steps`, `workflow_instances`)

## Conversion notes (ADR 0001)

The original spec named NestJS files (`routes/route-plan.ts`, `routes.service.ts`, Zod, Vitest). This version maps
them onto the Python approvals module as built by APPROVALS-01/02/05/08/09. It **extends** that engine and does not
fork it: route completion goes through the same transition internals (graph check, guard, sign-off assurance, hash
chain, `workflow.transitioned`) as `POST /instances/{id}/transition`. Workflows without a route behave exactly as
before, and the APPROVALS-09 golden cases are unchanged. Deviations from the original text (recorded in ADR 0040):

- The decide permission is **`approvals.approve`**, not `approvals.decide`: under ADR 0027 the verb `approve` is
  granted at the `approve` level, including the sign-off-only Client Reviewer role that INSPECTIONS-05 needs.
  `decide` is no verb and would be admin-only.
- A reject without a comment is **422 `COMMENT_REQUIRED`** (ADR 0035 §7), not 400.
- A role approver's `approver_ref` is the role's **id** (the data model's uuid column), resolved to its code
  through `access/api.py` at decision time.
- Route actions must be legal from the instance's state when the route starts (422 `ROUTE_ACTION_INVALID`). While a
  route runs, its two actions cannot be taken through `/transition` (409 `ROUTE_PENDING`); any other transition that
  moves the instance cancels the route (open steps become `skipped`).
- A critical completion transition runs the identity sign-off check for the last decider: `step_up_required` is
  401, `countersign_required` is 403 `COUNTERSIGN_ASSURANCE_REQUIRED` (route decisions are not countersigned).
- A finished route can be followed by a new one (rework, resubmit): steps carry a `route_round`, and
  `GET /instances/{id}/steps` returns the latest round.

## Spec

Attach a review chain to a workflow instance. The chain is ordered groups of user, role or team approver steps, run
serially or in parallel. When it finishes, it drives the instance's transition and writes the outcome back to the
host record through events (tag: extend; AIP spec E4-S3/S4, PRD 7.3: review chain).

- **files**:
  - `apps/api/migrations/versions/<timestamp>_approvals_routes.py`
  - `apps/api/aip/modules/approvals/tables.py` (new tables and columns)
  - `apps/api/aip/modules/approvals/routes_engine/route_plan.py` (pure)
  - `apps/api/aip/modules/approvals/routes_engine/eligibility.py`
  - `apps/api/aip/modules/approvals/routes_engine/repository.py`
  - `apps/api/aip/modules/approvals/routes_engine/service.py`
  - `apps/api/aip/modules/approvals/transition.py` (shared completion path; route guard on `/transition`)
  - `apps/api/aip/modules/approvals/routes.py`, `schemas.py`, `events.py`, `api.py`, `manifest.toml`
  - `apps/api/aip/modules/access/api.py`, `teams_api.py` (small read exports: `role_code_for_id`, `get_team_ref`)
  - `apps/api/aip/modules/approvals/tests/test_route_plan.py`, `test_eligibility.py`, `test_routes_db.py`
  - regenerated: `db/schema.snapshot.sql`, `packages/contracts/events/approval.*.v1.json`,
    `packages/contracts/src/permissions.generated.ts`, `packages/api-client/*`
  - `apps/api/tests/access/idor_routes.toml`, `apps/api/tests/isolation/overrides.toml` (if a check needs values)
- **steps**:
  - 1. Migration (forward-only raw SQL, ADR 0002):
    - `approval_route_templates` from the tenant-table template: `name`, `record_type`, `conditions jsonb`,
      `threshold_bands jsonb NULL`, `escalation_hours int NULL`, `version int`, `on_approved_action`,
      `on_rejected_action`, `allow_self_approval boolean default false`, `created_by`. FORCE RLS, fail-closed
      policy, soft delete.
    - `approval_steps` from the same template: `route_template_id`, `instance_id NULL` (a template step has none,
      a materialised step has one), `route_round`, `step_order`, `mode` (`serial|parallel`), `approver_type`
      (`user|role|team`), `approver_ref uuid`, `required_discipline_id NULL` (unused), `due_hours NULL` (template),
      `due_at NULL` (instance), `status` (`waiting|pending|approved|rejected|skipped`, NULL on a template step),
      `decided_by`, `decided_at`. Indexes from data-model.md: `(tenant_id, instance_id, step_order)`,
      `(tenant_id, approver_type, approver_ref, status)` for the inbox, `(tenant_id, due_at) WHERE status = 'pending'`.
    - `workflow_instances` gains `route_template_id`, `current_step_id`, `route_round` and `route_submitted_by`;
      index `(tenant_id, current_step_id)`.
    - `threshold_bands`, `escalation_hours` and `conditions` are created but unused: threshold bands, escalation,
      reminders and delegation are R1/P1 stubs (one `todo` board row each).
  - 2. `route_plan.py` is pure. Steps that share `step_order` form one group; a group of more than one step must be
    all `parallel` (422 at template creation). A group completes when **all** its steps approve.
    `next_action(steps, decision)` returns `Activate(order)`, `Wait()`, `Complete("approved")` or
    `Complete("rejected", skip=[ids])`. The first rejection rejects the whole route, and every undecided step
    (pending siblings and waiting later groups) becomes `skipped`.
  - 3. `eligibility.py`: `is_eligible(directory, actor_id, step, project_id)`:
    - `user`: `approver_ref == actor_id`.
    - `role`: the actor holds the role tenant-wide or on the instance's project (`access.api.has_role`).
    - `team`: the actor is a live member of the live team, and the team is tenant-level or on the instance's
      project (`access.api.teams_for_user`).

    Evaluated at decision time, never snapshotted. Separation of duties: unless the template sets
    `allow_self_approval`, the route's submitter (the actor of the instance's last applied decision when the route
    started, else whoever started it) cannot decide any step (403 `SELF_APPROVAL_FORBIDDEN`).
  - 4. `service.py` (`RoutesService`):
    - `start_route(conn, actor, instance_id, route_template_id)`: `approvals.start` on the instance's project;
      404 for an unknown template; 409 `ROUTE_ACTIVE` while a route runs; 422 `ROUTE_TEMPLATE_MISMATCH` when the
      template's record type differs; 422 `ROUTE_ACTION_INVALID` when either action is not legal from the current
      state. Copies the template steps into instance steps (new round), sets the first group `pending` with
      `due_at = now + due_hours`, the rest `waiting`, and emits `approval.requested` v1 per activated step.
    - `decide(conn, actor, instance_id, step_id, decision, comment)`:
      - locks the instance `FOR UPDATE`; `approvals.view` and `approvals.approve` on its project (403);
      - 404 when the step is not on the instance; 409 `STEP_NOT_PENDING` when it is decided or skipped;
        403 `NOT_CURRENT_APPROVER` when it is waiting or the actor is not eligible; 403 `SELF_APPROVAL_FORBIDDEN`;
      - 422 `COMMENT_REQUIRED` for a reject without a non-blank comment;
      - applies `next_action`. A completing decision runs the transition internals for `on_approved_action` or
        `on_rejected_action` (graph check, guard, sign-off) **before any write**, then appends one hash-chained
        history row with `step_id` (the transition row), moves the instance and emits `workflow.transitioned`,
        `approval.approved` or `approval.rejected`, and `approval.completed` `{instanceId, recordType, recordId,
        outcome}`, all in the same transaction. A non-completing decision appends a history row with
        `from_state == to_state` and action `approve_step` or `reject_step`, and activates the next group if due.
    - `steps(conn, actor, instance_id)` and `pending_steps(conn, actor)` (the inbox query APPROVALS-06 uses).
  - 5. Endpoints under `/api/v1/approvals` (Pydantic models, camelCase, unknown keys refused with 422):
    - `POST /route-templates` and `GET /route-templates` (`approvals.design`)
    - `POST /instances/{id}/route {routeTemplateId}` (`approvals.start`)
    - `POST /instances/{id}/decide {stepId, decision, comment?}` (`approvals.approve`)
    - `GET /instances/{id}/steps` (`approvals.view`)
  - 6. Export `start_route`, `decide`, `steps` and `pending_steps` from `ApprovalsApi` in `api.py`.
- **acceptance**:
  - A serial route only accepts the current step's approver.
  - A parallel group needs every step, and one rejection ends the route.
  - Role and team approvers are resolved at decision time, inside the instance's project.
  - Self-approval is refused by default.
  - Completion moves the instance state and emits the outcome events in the same transaction as the last decision.
  - Instances without a route, and the APPROVALS-09 golden cases, behave exactly as before.
- **tests**:
  - **unit** (`test_route_plan.py`, `test_eligibility.py`):
    - Steps `[{order:1, serial, user U1}, {order:2, parallel, role QA}, {order:2, parallel, team Client}]` → groups
      `[[s1],[s2,s3]]`.
    - After s1 approves → `Activate(2)`. After s2 approves (s3 pending) → `Wait()`. After s3 approves →
      `Complete("approved")`.
    - s2 rejects while s3 is pending → `Complete("rejected", skip=[s3])`.
    - Two serial steps sharing an order → refused.
    - `is_eligible` for an actor with role QA on project P1, a step with role QA, and an instance in P2 → `False`.
  - **integration** (`test_routes_db.py`, Testcontainers Postgres, `kaefer-demo` fixtures, real role and team rows):
    - Serial route U1 then U2 on a `demo` instance submitted by U3. U2 decides first → 403 `NOT_CURRENT_APPROVER`.
      U1 approves → step 1 `approved`, step 2 `pending`, and `approval.requested` for U2. U2 approves → the
      instance is `approved`, with one `approval.approved` event and one `approval.completed` event.
    - A parallel group of role QA and team Client. A Client team member rejects with comment
      `'paint DFT out of spec'` → the instance is `rejected`, the QA step is `skipped`, and there is exactly one
      `approval.rejected` event.
    - A reject with no comment → 422 `COMMENT_REQUIRED`.
    - The team approver is removed from team Client (ACCESS-04 API) before deciding → 403.
    - The submitter U3 is also the step-1 user approver → 403 `SELF_APPROVAL_FORBIDDEN`. With
      `allow_self_approval: true` → 200.
    - Deciding an already-approved step again → 409.
    - A `tenant-b` user deciding a `kaefer-demo` step → 404.
    - History for the serial flow has 3 rows (submit, then 2 decisions), and the chain verifies.
    - While the route runs, `/transition` with its approve action → 409 `ROUTE_PENDING`.
  - **e2e**: the Playwright API journey (submit, approver 1, approver 2, both steps `approved`) is carried with the
    approvals inbox to APPROVALS-06, as ADR 0035 §9 did for APPROVALS-02: the deployed `demo` seed has no route
    template or second approver fixture yet. The integration tests run the same HTTP journey in-process.
