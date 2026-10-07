# APPROVALS-05 — Inspection lifecycle preset + golden tests (needs AIP lifecycle spec)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`approvals`](../../docs/blueprint/modules/approvals/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | APPROVALS-02, TERMS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/approvals/README.md`](../../docs/blueprint/modules/approvals/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md) (`config/workflows/`, `config/terms/en-AU/`), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (AIP stays live; inspections are R1)
4. Lifecycle source: [`inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) ("Features" first bullet and "Decisions and notes"), plus the walkthrough at the end of [`inspections/features-access.md`](../../docs/blueprint/modules/inspections/features-access.md)

> **Owner confirmation required.** The AIP source (TASKS 8.2, spec E4-S3/S4, PRD §7.3 and the AIP
> lifecycle tests) is **not in this repo** ([OPEN-QUESTIONS.md](../OPEN-QUESTIONS.md) #4). Until the
> owner supplies it or signs off the golden cases below, the cases are **provisional**, derived only from
> the blueprint. This task may reach `review` but **must not be marked `done`** until the owner has
> confirmed the golden cases in the PR, or until the cases have been regenerated from the AIP lifecycle
> tests and every difference is listed in the PR.

## Spec

Ship the inspection review chain as data. It has two preset definitions (standard, and with client review), neutral state and action codes, en-AU term keys, and golden lifecycle tests that run through the real transition service (tag: port — AIP hard-coded inspection lifecycle, TASKS 8.2 / E4-S3/S4; blocked on the AIP source as noted above).

- **files**:
  - config/workflows/inspection.standard.json
  - config/workflows/inspection.client-review.json
  - config/terms/en-AU/ (add `workflow.inspection.*` keys in the file format TERMS-01 established)
  - apps/api/src/modules/approvals/presets/preset-loader.ts
  - apps/api/src/modules/approvals/presets/presets.controller.ts
  - apps/api/src/modules/approvals/manifest.json
  - apps/api/src/modules/approvals/tests/golden/inspection-lifecycle.cases.json
  - apps/api/src/modules/approvals/tests/golden/inspection-lifecycle.spec.ts
  - apps/api/src/modules/approvals/tests/presets.int.spec.ts
- **steps**:
  - 1. Write the provisional lifecycle into both preset files. Both are valid `WorkflowDefinitionSpec` (APPROVALS-01) with `recordType: "inspection"`.
     - States: `draft` (initial), `assignable`, `assigned`, `in_progress`, `inspector_review`, `supervisor_review`, `client_review` (client-review variant only), `rejected`, `completed` (terminal).
     - Standard transitions:
       - `ready` draft→assignable
       - `assign` assignable→assigned
       - `unassign` assigned→assignable
       - `start` assigned→in_progress
       - `submit` in_progress→inspector_review
       - `review_pass` inspector_review→supervisor_review
       - `approve` supervisor_review→completed (critical)
       - `reject` from inspector_review or supervisor_review →rejected (comment required: add an optional `requiresComment: boolean` to the transition schema, and have `transition()` return 400 `COMMENT_REQUIRED` when it is set and no comment is given)
       - `resend` rejected→assigned
     - The client-review variant replaces `approve` with supervisor_review→client_review (not critical) and adds `client_approve` client_review→completed (critical) and `reject` client_review→rejected.
     - Re-inspect is **not** a transition. `completed` is terminal, and a re-inspection is a new inspection and instance created by the R1 inspections module. Write that as a stub note in the PR.
     - Any reviewer who spots a lifecycle that differs from AIP should change only the JSON and golden cases, never engine code.
  - 2. Choose between client review and no client review **per project** by installing the client-review variant as a project-scoped definition (APPROVALS-01 resolution order). Do not use guards here, because APPROVALS-03 is not a dependency.
  - 3. Permissions: declare `approvals.inspection.assign`, `approvals.inspection.execute`, `approvals.inspection.review`, `approvals.inspection.approve` and `approvals.inspection.client_approve` in `approvals/manifest.json`. Each transition's `requiredPermission` uses one of them. The R1 inspections tasks may move them to the inspections manifest.
  - 4. Terms: add `workflow.inspection.state.<code>` and `workflow.inspection.action.<code>` en-AU keys (e.g. `supervisor_review` → "Supervisor review", `client_approve` → "Client approve") through the TERMS-01 dictionary and loader. The preset files contain only keys and codes, never display text.
  - 5. `preset-loader.ts`:
     - `listPresets()` reads `config/workflows/*.json` and validates each file at boot (fail fast).
     - `installPreset(presetKey, projectId?)` creates and publishes a definition with `is_preset = true` and key `inspection`. It is idempotent: installing the same preset version again does nothing.
     - Expose `GET /api/v1/approvals/presets` and `POST /api/v1/approvals/definitions/from-preset {presetKey, projectId?}` (`approvals.design`).
     - Seed `inspection.standard` for the `kaefer-demo` fixture tenant.
  - 6. Golden cases: `inspection-lifecycle.cases.json` has a header `{"source": "blueprint (provisional)", "confirmedBy": null, "confirmedOn": null}` and an array of `{name, variant, start, actions[], expect: {state} | {error}}`. The spec file runs each case twice: through the pure evaluator, and through `TransitionService` against Postgres. While `confirmedBy` is null, it prints a visible `PROVISIONAL golden cases — owner confirmation pending` warning.
- **acceptance**:
  - Both presets load and validate at boot, and every state and action has an en-AU term key.
  - Every golden case passes through both the evaluator and the transition service.
  - `approve` and `client_approve` need MFA or step-up (critical).
  - Projects with the client-review variant go through `client_review`, and the others do not.
  - The PR states whether the cases were confirmed by the owner or regenerated from AIP. The board status stays `review` until they are.
- **tests**:
  - **unit**:
    - Both preset files parse with `WorkflowDefinitionSpec`, and all their states are reachable.
    - Every `labelKey` in both presets exists in the en-AU dictionary → 0 missing keys.
    - Golden `standard-happy-path`: draft →ready→ assignable →assign→ assigned →start→ in_progress →submit→ inspector_review →review_pass→ supervisor_review →approve→ `completed`.
    - Golden `client-happy-path` (client variant): … supervisor_review →approve→ client_review →client_approve→ `completed`.
    - Golden `approve-too-early`: from `inspector_review`, `approve` → `INVALID_TRANSITION`.
    - Golden `reject-and-resend`: supervisor_review →reject→ rejected →resend→ assigned →start→ `in_progress`.
    - Golden `client-cannot-skip`: client variant, `approve` from `client_review` → `INVALID_TRANSITION`.
    - Golden `unassign`: assigned →unassign→ `assignable`.
    - Golden `completed-is-final`: `availableTransitions` at `completed` → `[]`.
  - **integration**:
    - These use Testcontainers Postgres. `installPreset('inspection.standard')` for `kaefer-demo`, with the fixture users supervisor (assign, approve), inspector (execute), lead inspector (review) and client reviewer (client_approve). Run `standard-happy-path` through `TransitionService` with the supervisor at `authStrength 'mfa'`. Expected: every step 200, 7 history rows, and `verifyChain` ok.
    - The inspector attempts `approve` at `supervisor_review` → 403.
    - The supervisor attempts `approve` with `authStrength 'password'` → 403 `STEP_UP_REQUIRED`.
    - Install `inspection.client-review` for project `RT-01` only. An instance in `RT-01` reaches `client_review` after `approve`, and an instance in project `KF-01` reaches `completed`.
    - `installPreset` twice → 1 active definition, version 1.
  - **e2e**:
    - Playwright API project. A `kaefer-demo` tenant admin calls `POST /api/v1/approvals/definitions/from-preset {presetKey:'inspection.standard'}`. Then `GET /api/v1/approvals/presets` lists both presets, and `GET /instances/:id` for a new inspection instance returns `current_state:'draft'` with `availableTransitions[0].labelKey:'workflow.inspection.action.ready'`.
