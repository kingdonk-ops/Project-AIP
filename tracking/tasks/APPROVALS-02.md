# APPROVALS-02 — Transition service: policy check, version pinning, hash-chained decisions, JSONLogic guards, events

<!-- hand-edited: merged APPROVALS-03 (Part B) per board slim 2026-10-17 -->
<!-- hand-edited: sign-off assurance per ADR 0010 -->
<!-- hand-edited: built on the Python backend; ADR 0035 records where the code differs from this NestJS-era text -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, APPROVALS-01, AUDIT-01, IDENTITY-04 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (`withTenant`, append-only grants), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction), [0005](../../docs/adr/0005-identity-architecture.md) (session auth strength), [0004](../../docs/adr/0004-repository-layout.md) (only `api.ts` crosses modules)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/approvals/data-model.md) (`workflow_decision_history`); for Part B future direction: [`rules/README.md`](../../docs/blueprint/modules/rules/README.md) (the full rules engine is R1/P1, **not** this task)

> Part A (was APPROVALS-02) is the transition service, hash chain and events. Part B (was APPROVALS-03) is the
> minimal server-side JSONLogic guard that Part A's step (f) leaves a slot for. Part B only extended Part A, so
> they are one task.

## Part A — transition service (was APPROVALS-02)

Make one server-side transition path. It loads the instance's pinned definition, asks the policy service, applies the sign-off assurance check (ADR 0010) on critical transitions, appends a hash-chained decision row and writes the outbox event, all in one transaction (tag: extend).

- **files**:
  - db/migrations/<timestamp>_approvals_decision_history.sql
  - apps/api/src/modules/approvals/transition.service.ts
  - apps/api/src/modules/approvals/decision-chain.ts
  - apps/api/src/modules/approvals/controller.ts
  - apps/api/src/modules/approvals/events.ts
  - apps/api/src/modules/approvals/permissions.ts
  - apps/api/src/modules/approvals/api.ts
  - apps/api/src/modules/approvals/tests/decision-chain.spec.ts
  - apps/api/src/modules/approvals/tests/transition.int.spec.ts
  - e2e/web/approvals-transition.spec.ts
- **steps**:
  - 1. Migration: create `workflow_decision_history` with the data-model columns and `unique (instance_id, seq)`. It is append-only: no `updated_at` or `deleted_at`, and `REVOKE UPDATE, DELETE, TRUNCATE ... FROM aip_app`. Add FORCE RLS with the fail-closed tenant policy.
  - 2. `decision-chain.ts`:
    - `entryHash(entry)` is `sha256` (hex) over canonical JSON (sorted keys, no whitespace) of `{tenant_id, instance_id, seq, from_state, to_state, action, actor_id, on_behalf_of, comment, auth_strength, ip_address, guard_result, step_id, created_at, prev_hash}`.
    - Genesis `prev_hash` is `sha256('genesis:' + instance_id)`.
    - Reuse AUDIT-01's canonical-JSON helper if `audit/api.ts` exports one. Never read or write audit tables.
    - `verifyChain(entries)` returns `{ok: true}` or `{ok: false, brokenAtSeq}`.
  - 3. `transition.service.ts`: `transition(ctx, instanceId, {action, comment?, expectedSyncVersion?})` runs inside one `withTenant` transaction:
    - (a) `SELECT ... FOR UPDATE` the instance. A missing instance or another tenant's instance gives 404.
    - (b) Load the definition by `instance.definition_id`, never the active one.
    - (c) Call `evaluator.applyTransition`. If it fails, return 409 `INVALID_TRANSITION`.
    - (d) Call `PolicyService.can(ctx.actor, transition.requiredPermission, {projectId, recordType, recordId})` (ACCESS-01). On deny, return 403 with nothing written.
    - (e) If `transition.critical`, call `identity.api.check_signoff_assurance(ctx, transition.action_code)` (IDENTITY-04 Part D, ADR 0010). `step_up_required` → 403 `STEP_UP_REQUIRED` with `stepUpUrl`. `countersign_required` → record the decision with status `pending_countersign`; the transition does NOT take effect until a countersign decision by a different user who passes the check. `allow` → proceed. Store the returned `assurance_level`, `method`, `authenticated_at` and `device_id` on the decision row. Do not build a step-up UI here.
    - (f) Evaluate the transition's JSONLogic guard (Part B) after the policy check and before any write. Insert a history row with `seq = last + 1`, the chained hash, the client IP from the context, and `guard_result` from Part B.
    - (g) Update `current_state` and `sync_version` through DATABASE-04 `updateWithVersion`. A mismatched `expectedSyncVersion` gives 409.
    - (h) Call `emit(tx, 'workflow.transitioned', 1, ...)` (ARCH-05) with payload `{instanceId, recordType, recordId, projectId, from, to, action, actorId, definitionKey, definitionVersion}`.
  - 4. Retro-fit `definitions.service.publish` to emit `workflow.definition_published` v1 in the same transaction.
  - 5. Controller under `/api/v1/approvals`, all routes with permission decorators (deny by default):
    - `POST /instances {recordType, recordId, projectId}` (`approvals.start`)
    - `GET /instances/:id`, which returns state, pinned version and `availableTransitions` for the caller (each with `{allowed, reasonKey}` from Part B)
    - `POST /instances/:id/transition {action, comment?, expectedSyncVersion?}`
    - `GET /instances/:id/history`, which returns entries plus `chainValid`

    Validate request bodies with strict Zod schemas (nestjs-zod), so unknown keys give 400.
  - 6. Export `startInstance`, `transition`, `availableTransitions` and `getHistory` from `api.ts` for host modules. Declare the events in `manifest.json` and their Zod payloads in `events.ts`.
- **acceptance**:
  - Every successful transition writes exactly one history row and one `domain_events` row in the same transaction. A forced failure after the history insert leaves neither.
  - A denied or illegal transition writes nothing.
  - In-flight instances keep using their pinned version after a newer version is published.
  - `GET /history` reports `chainValid: true`. Altering any stored field (as the owner role in the test) makes it report `false`.
  - The OpenAPI client regenerates without drift (STACK-03).
- **tests**:
  - **unit**:
    - `entryHash` of the same entry with keys in a different order → identical hash. Changing `comment` from `'ok'` to `'ok.'` → a different hash.
    - `verifyChain([e1, e2, e3])` with `e2.comment` altered → `{ok:false, brokenAtSeq: 2}`. An empty chain → `{ok:true}`.
    - Critical-transition check (with `check_signoff_assurance` stubbed): `step_up_required` → 403 `STEP_UP_REQUIRED`; `countersign_required` → decision `pending_countersign` and the instance state is unchanged; a countersign by the same user → 409 `SELF_COUNTERSIGN`; a countersign by a supervisor returning `allow` → the transition applies and both assurance records are stored; `allow` → applied, with `method` recorded.
  - **integration**:
    - These run with Testcontainers Postgres and the TESTING-01 fixtures `kaefer-demo` and `tenant-b`, using the `demo` definition from APPROVALS-01. A user with `approvals.demo.submit` POSTs `transition {action:'submit'}` → 200 with `current_state: 'submitted'`. History has `seq 1` with `prev_hash = sha256('genesis:'+id)`, and `domain_events` has 1 `workflow.transitioned` row.
    - A viewer without `approvals.demo.submit` → 403. The history and `domain_events` counts are unchanged.
    - `action:'approve'` from `draft` → 409 `INVALID_TRANSITION`.
    - Publish v2 without the `reject` transition. An instance pinned to v1 in `submitted` can still `reject` → 200.
    - Make the test hook in `emit` throw → 500. The instance is still `draft` and history has 0 rows.
    - Fire two transitions on the same instance with `Promise.all` → one 200 and one 409. History has 1 row.
    - As `aip_app`: `UPDATE workflow_decision_history SET comment='x'` → `permission denied`, and `DELETE` → `permission denied`.
    - A `tenant-b` user calling `GET /api/v1/approvals/instances/{kaefer instance id}` → 404.
    - A body with an unknown key `{"action":"submit","guardResult":true}` → 400.
  - **e2e**:
    - Playwright API project. Sign in as the `kaefer-demo` submitter fixture, `POST /instances`, transition `submit`, then `GET /history`. Expected: 1 entry, a 64-hex `entry_hash`, and `chainValid: true`. The same GET as a `tenant-b` user → 404.

## Part B — minimal server-side JSONLogic guards (merged from APPROVALS-03)

Evaluate each transition's JSONLogic guard on the server, using read-only facts from host-module context providers, and fail closed on errors (tag: extend — AIP PRD §7.3 server-side guard expressions).

- **files**:
  - apps/api/src/modules/approvals/guards/jsonlogic.ts
  - apps/api/src/modules/approvals/guards/context-providers.ts
  - apps/api/src/modules/approvals/transition.service.ts
  - apps/api/src/modules/approvals/schemas.ts
  - apps/api/src/modules/approvals/api.ts
  - apps/api/src/modules/approvals/tests/jsonlogic.spec.ts
  - apps/api/src/modules/approvals/tests/guards.int.spec.ts
- **steps**:
  - 1. Wrap `json-logic-js` in `guards/jsonlogic.ts`:
    - Operator allow-list: `== != === !== < <= > >= ! !! and or if var missing missing_some in`.
    - Reject `some all none map reduce filter merge method` and any custom operator.
    - Limits: depth ≤ 20, node count ≤ 200, serialised size ≤ 8 KB.
    - Export `validateGuard(expr)` and `evaluateGuard(expr, data)`. `evaluateGuard` deep-freezes `data` and never registers operations.
  - 2. Call `validateGuard` from `WorkflowDefinitionSpec` (`schemas.ts`), so a bad guard fails `createDraft` and `updateDraft` with a path such as `['transitions', 1, 'guard']`.
  - 3. `guards/context-providers.ts`: `registerGuardContextProvider(recordType, (ctx, recordId) => Promise<Record<string, unknown>>)`, exported through `api.ts`. Host modules register read-only facts this way. There are no cross-module table reads. If no provider is registered, `record` is `{}`.
  - 4. Guard data shape: `{record: <provider facts>, actor: {id, roles: string[]}, instance: {state, projectId, recordType}}`.
  - 5. In `transition()` step (f), evaluate the guard after the policy check and before any write:
    - `false` → 422 `GUARD_FAILED` with `messageKey = transition.guardMessageKey ?? 'approvals.guard.failed'`.
    - A provider throw or evaluation exception → 422 `GUARD_ERROR` (fail closed, logged with the instance id, never the record payload).
    - On success, store `guard_result = {passed: true, guard, factsHash: sha256(canonical facts)}` in the history row.
  - 6. `availableTransitions` in `GET /instances/:id` adds `{allowed, reasonKey}` per transition, computed on the server. Clients never send guard outcomes: strict body schemas already reject them, and a test proves it.
- **acceptance**:
  - A transition whose guard evaluates false is refused with 422, and no history or outbox row is written.
  - Only allow-listed operators can be saved or evaluated.
  - Guard errors fail closed.
  - The history row records the guard and a hash of the facts it saw.
- **tests**:
  - **unit**:
    - `evaluateGuard({"==":[{"var":"record.openCriticalIssues"},0]}, {record:{openCriticalIssues:0}})` → `true`. With `openCriticalIssues: 2` → `false`.
    - `validateGuard({"some":[{"var":"record.items"},{"==":[{"var":""},1]}]})` → error `operator not allowed: some`.
    - `validateGuard({"exec":["rm -rf /"]})` → error `operator not allowed: exec`.
    - An `and` nested 25 deep → error `guard too deep`.
    - `evaluateGuard` with `data` mutated inside a custom test operator → throws (frozen). The allow-list is restored after the test.
  - **integration**:
    - Definition `demo` with guard `{"==":[{"var":"record.allPhotosClean"},true]}` on `approve` and a test provider for `demo` that returns `{allPhotosClean:false}`. POST `transition approve` → 422 `GUARD_FAILED`, and history is unchanged. With the provider returning `true` → 200, and history `guard_result.passed = true` with a 64-hex `factsHash`.
    - A provider that throws `Error('db down')` → 422 `GUARD_ERROR`, and the state is unchanged.
    - `createDraft` with a guard using `reduce` → 400 with the issue path `transitions[1].guard`.
    - `GET /api/v1/approvals/instances/:id` while the guard is false → the `approve` entry has `allowed:false` and `reasonKey:'approvals.guard.photos_not_clean'`.
  - **e2e**:
    - Playwright API project on the compose stack (`kaefer-demo`). Run the guarded `demo` flow: approve is refused with 422. After the fixture flips `allPhotosClean`, approve → 200, and `GET /history` shows `chainValid: true`.
