# APPROVALS-03 — Server-side JSONLogic transition guards (minimal)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | APPROVALS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md) (only `api.ts` crosses modules)
4. Only for future direction: [`rules/README.md`](../../docs/blueprint/modules/rules/README.md). The full rules engine (rule sets, versioning, waivers) is R1/P1, **not** this task.

## Spec

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
  - 5. In `transition()`, evaluate the guard after the policy check and before any write:
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
