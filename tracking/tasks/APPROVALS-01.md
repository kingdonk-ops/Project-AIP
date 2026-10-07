# APPROVALS-01 — Versioned workflow definitions/instances + pure state-machine evaluator

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-02, DATABASE-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (Kysely, `db/migrations`, `withTenant`), [0004](../../docs/adr/0004-repository-layout.md) (module layout)
4. Only for column lists: [`data-model.md`](../../docs/blueprint/modules/approvals/data-model.md) (`workflow_definitions`, `workflow_instances`, `workflow_definition_audit`)

## Spec

Store workflow definitions as versioned data, pin each instance to the version it started on, and decide legal transitions with a pure, I/O-free evaluator (tag: extend — generalises AIP's hard-coded inspection lifecycle, which APPROVALS-05 ports).

- **files**:
  - db/migrations/<timestamp>_approvals_workflows.sql
  - apps/api/src/modules/approvals/manifest.json
  - apps/api/src/modules/approvals/module.ts
  - apps/api/src/modules/approvals/api.ts
  - apps/api/src/modules/approvals/schemas.ts
  - apps/api/src/modules/approvals/engine/evaluator.ts
  - apps/api/src/modules/approvals/definitions.repository.ts
  - apps/api/src/modules/approvals/definitions.service.ts
  - apps/api/src/modules/approvals/instances.service.ts
  - apps/api/src/modules/approvals/tests/evaluator.spec.ts
  - apps/api/src/modules/approvals/tests/definitions.int.spec.ts
- **steps**:
  - 1. Scaffold the module with `tools/new-module.ts approvals` (ARCH-01). In `manifest.json` declare `id: "approvals"`, `dependsOn: []` and the permissions `approvals.view` and `approvals.design`. Do not add HTTP routes in this task.
  - 2. Write one migration from the `db/templates/` tenant-table template with three tables. **`workflow_definitions`** has the data-model columns, `unique (tenant_id, key, version)`, a partial unique index `(tenant_id, key, coalesce(project_id, '00000000-0000-0000-0000-000000000000'::uuid)) where status = 'active'` (at most one active version per key and scope), and a `status` check of `draft|active|retired`. **`workflow_instances`** has `definition_id` as an FK to the pinned version, `current_state`, `sync_version`, `created_by` and `unique (tenant_id, record_type, record_id) where deleted_at is null`. **`workflow_definition_audit`** is append-only: no `updated_at` or `deleted_at`, with `REVOKE UPDATE, DELETE, TRUNCATE ... FROM aip_app`. All three tables get `FORCE ROW LEVEL SECURITY` with the fail-closed `NULLIF(current_setting('app.tenant_id', true), '')::uuid` policy in `USING` and `WITH CHECK`. Route, step and decision tables are out of scope (they come in APPROVALS-02 and APPROVALS-04).
  - 3. In `schemas.ts`, define the Zod `WorkflowDefinitionSpec`: `states: [{code, labelKey, terminal?}]`, `initial`, and `transitions: [{action, from, to, requiredPermission, guard: JsonLogic | null, sideEffects: [], critical: boolean, labelKey}]`. Validate:
    - codes and actions match `^[a-z][a-z0-9_]*$`
    - `labelKey` is a term key (`^[a-z0-9_.]+$`), never display text
    - `initial`, `from` and `to` are declared states
    - `(from, action)` is unique
    - terminal states have no outgoing transitions
    - every state is reachable from `initial`

    Store `guard` but do not evaluate it here (APPROVALS-03 does that).
  - 4. Write `engine/evaluator.ts` as pure functions with no DB, clock or randomness:
    - `availableTransitions(spec, state, grantedPermissions: ReadonlySet<string>)` filters by state and by permission. It only produces UI hints. The authoritative check is APPROVALS-02.
    - `applyTransition(spec, state, action)` returns `{ok: true, from, to, transition}` or `{ok: false, error: 'INVALID_TRANSITION' | 'UNKNOWN_STATE'}`.
  - 5. In `definitions.service.ts`, inside `withTenant`:
    - `createDraft(key, recordType, projectId?, spec)` creates version `max(version) + 1`.
    - `updateDraft` works only while the status is `draft`. Active and retired versions throw `DefinitionImmutableError`.
    - `publish(id)` retires the previous active version for the same key and scope, activates this one, and writes a `workflow_definition_audit` row with a `{before, after}` diff, all in one transaction.
  - 6. `getActiveDefinition(recordType, projectId?)` returns the project-specific active definition first, then the tenant-wide one, and throws `NoActiveDefinitionError` if neither exists.
  - 7. `instances.service.ts` `startInstance(recordType, recordId, projectId)` pins `definition_id` to the version that is active at that moment and sets `current_state = spec.initial`. It is idempotent: a second call for the same record returns the existing row. Transitions on instances are APPROVALS-02.
  - 8. Export only `startInstance`, `getActiveDefinition`, `availableTransitions` and the spec types from `api.ts`.
- **acceptance**:
  - Publishing v2 of a key never changes `definition_id` on instances started under v1.
  - An invalid spec is rejected with a Zod issue at the exact path. Active and retired definitions cannot be edited.
  - The evaluator has no imports from `platform/db` and reaches 100% branch coverage.
  - All three tables pass the TESTING-02 schema guard (tenant_id, FORCE RLS), and tenant B and unset-context reads return 0 rows.
- **tests**:
  - **unit**:
    - Fixture spec `demo`: states `draft, submitted, approved (terminal), rejected`; transitions `submit draft→submitted`, `approve submitted→approved`, `reject submitted→rejected`, `resubmit rejected→submitted`. `availableTransitions(demo, 'draft', {'approvals.demo.submit'})` → `['submit']`.
    - `applyTransition(demo, 'draft', 'approve')` → `{ok:false, error:'INVALID_TRANSITION'}`. `applyTransition(demo, 'submitted', 'approve')` → `{ok:true, to:'approved'}`.
    - A spec with a transition `to: 'archived'` (undeclared) → Zod issue at `['transitions', 0, 'to']`.
    - A spec with state `orphan` that cannot be reached → issue message `unreachable state: orphan`.
    - A state with `labelKey: 'Draft'` → rejected (not a term key).
    - A terminal state `approved` with an outgoing transition → rejected.
    - fast-check: for any valid generated spec and any action sequence, `applyTransition` never returns a `to` outside `spec.states`.
  - **integration**:
    - These run with Testcontainers Postgres as `aip_app`. Publish `demo` v1, start an instance for record R1, publish v2 (which adds `on_hold`), then start an instance for R2. Expected: R1 is pinned to v1.id, R2 to v2.id, v1 is `retired` and v2 is `active`.
    - `updateDraft` on v2 after publish → `DefinitionImmutableError`. `UPDATE workflow_definition_audit` as `aip_app` → `permission denied`.
    - Call `startInstance` twice for R1. Expected: the same id and one row.
    - A tenant-wide `demo` plus a project P1 override: resolve for P1 → the P1 definition; resolve for P2 → the tenant-wide one; no active definition for `issue` → `NoActiveDefinitionError`.
    - As tenant B, `select * from workflow_definitions` → 0 rows. With the tenant context unset → 0 rows, and an insert is rejected.
  - **e2e**:
    - None. This task has no HTTP route or page. The first approvals e2e lands in APPROVALS-02.
