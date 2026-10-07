# APPROVALS-04 — Approval routes: sequential/parallel steps, user/role/team approvers

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

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
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox events), [0004](../../docs/adr/0004-repository-layout.md) (teams and roles only via `access/api.ts`)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/approvals/data-model.md) (`approval_route_templates`, `approval_steps`)

## Spec

Attach a review chain to a workflow instance. The chain is ordered groups of user, role or team approver steps, run serially or in parallel. When it finishes, it drives the instance's transition and writes the outcome back to the host record through events (tag: extend).

- **files**:
  - db/migrations/<timestamp>_approvals_routes.sql
  - apps/api/src/modules/approvals/routes/route-plan.ts
  - apps/api/src/modules/approvals/routes/routes.service.ts
  - apps/api/src/modules/approvals/routes/approver-eligibility.ts
  - apps/api/src/modules/approvals/routes/routes.controller.ts
  - apps/api/src/modules/approvals/events.ts
  - apps/api/src/modules/approvals/api.ts
  - apps/api/src/modules/approvals/tests/route-plan.spec.ts
  - apps/api/src/modules/approvals/tests/routes.int.spec.ts
- **steps**:
  - 1. Migration: create `approval_route_templates` and `approval_steps` with the data-model columns. Add `workflow_instances.route_template_id` and `current_step_id` if APPROVALS-01 did not create them. Add `approval_route_templates.on_approved_action`, `on_rejected_action` and `allow_self_approval boolean default false`. Use FORCE RLS and the fail-closed policy. Keep the indexes from data-model.md, including `(tenant_id, approver_type, approver_ref, status)` for the inbox. Create the `threshold_bands` and `escalation_hours` columns, but leave them unused: threshold bands, escalation, reminders and delegation are R1/P1 stubs. Write a one-line stub task for each (feedback-loop rule).
  - 2. `routes/route-plan.ts` is pure. Steps that share `step_order` and have `mode: 'parallel'` form one group, and a group completes when **all** of its steps approve. `nextAction(steps, decision)` returns one of:
    - `{activate: groupN}`
    - `{complete: 'approved'}`
    - `{complete: 'rejected', skip: [ids]}`

    The first rejection rejects the whole route, and pending siblings become `skipped`.
  - 3. `routes/approver-eligibility.ts`: `isEligible(actor, step, instance)`:
    - `user`: `approver_ref = actor.id`.
    - `role`: the actor holds the role in the instance's project or tenant-wide (ACCESS-02 assignments via `access/api.ts`).
    - `team`: the actor is a current member (ACCESS-04 via `access/api.ts`).

    Evaluate this at decision time, not as a snapshot. Separation of duties: unless `allow_self_approval` is set, the actor who made the transition that started the route cannot decide any step (403 `SELF_APPROVAL_FORBIDDEN`).
  - 4. `routes.service.ts`:
    - `startRoute(instanceId, routeTemplateId)` copies the template steps into instance-bound `approval_steps` rows, sets the first group to `pending` with `due_at = now + due_hours`, and emits `approval.requested` per activated step.
    - `decide(ctx, instanceId, stepId, {decision: 'approve'|'reject', comment})`:
      - requires `PolicyService.can(actor, 'approvals.decide', scope)` and `isEligible`
      - requires a comment when rejecting
      - locks the instance `FOR UPDATE`
      - returns 409 if the step is not `pending`
      - appends a hash-chained history row with `step_id` (reusing APPROVALS-02 `decision-chain`)
      - applies `nextAction`
    - On completion, it calls the APPROVALS-02 transition internals with `on_approved_action` or `on_rejected_action` in the **same** transaction, then emits `approval.approved` or `approval.rejected` and `approval.completed` `{instanceId, recordType, recordId, outcome}`.
  - 5. Endpoints under `/api/v1/approvals`:
    - `POST /route-templates` and `GET /route-templates` (`approvals.design`)
    - `POST /instances/:id/route {routeTemplateId}` (`approvals.start`)
    - `POST /instances/:id/decide {stepId, decision, comment?}`
    - `GET /instances/:id/steps`

    Validate with strict Zod.
  - 6. Export `startRoute`, `decide` and `pendingStepsQuery(actor)` (the query builder APPROVALS-06 uses) from `api.ts`.
- **acceptance**:
  - A serial route only accepts the current step's approver.
  - A parallel group needs every step, and one rejection ends the route.
  - Role and team approvers are resolved at decision time, inside the instance's project.
  - Self-approval is refused by default.
  - Completion moves the instance state and emits the outcome events in the same transaction as the last decision.
- **tests**:
  - **unit**:
    - Steps `[{order:1, serial, user U1}, {order:2, parallel, role QA}, {order:2, parallel, team Client}]` → groups `[[s1],[s2,s3]]`.
    - After s1 approves → `{activate: 2}`. After s2 approves (s3 pending) → no completion. After s3 approves → `{complete:'approved'}`.
    - s2 rejects while s3 is pending → `{complete:'rejected', skip:[s3]}`.
    - `isEligible` for an actor with role QA on project P1, a step with role QA, and an instance in P2 → `false`.
  - **integration**:
    - These use Testcontainers Postgres with the `kaefer-demo` fixtures. Serial route U1 then U2 on a `demo` instance submitted by U3. U2 decides first → 403 `NOT_CURRENT_APPROVER`. U1 approves → step 1 `approved`, step 2 `pending`, and `approval.requested` for U2. U2 approves → the instance is `approved`, with one `approval.approved` event and one `approval.completed` event.
    - A parallel group of role QA and team Client. A Client team member rejects with comment `'paint DFT out of spec'` → the instance is `rejected`, the QA step is `skipped`, and there is exactly one `approval.rejected` event.
    - A reject with no comment → 400.
    - The team approver is removed from team Client (ACCESS-04 API) before deciding → 403.
    - The submitter U3 is also the step-1 user approver → 403 `SELF_APPROVAL_FORBIDDEN`. With `allow_self_approval: true` → 200.
    - Deciding an already-approved step again → 409.
    - A `tenant-b` user deciding a `kaefer-demo` step → 404.
    - History for the serial flow has 3 rows (submit, then 2 decisions), and `verifyChain` → ok.
  - **e2e**:
    - Playwright API project. Two `kaefer-demo` approver fixtures and a serial route: the submitter submits, approver 1 approves, approver 2 approves. `GET /instances/:id` → `current_state: 'approved'`, and `GET /instances/:id/steps` shows both steps `approved`.
