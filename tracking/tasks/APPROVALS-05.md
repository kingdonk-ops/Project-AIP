# APPROVALS-05 — Inspection lifecycle preset + golden tests (needs AIP lifecycle spec)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: converted to the Python backend per ADR 0001 (2026-10-28), on the APPROVALS-08 installer -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python layout), [0035](../../docs/adr/0035-transition-service-implementation.md) (422 for validation, 401 step-up), [0036](../../docs/adr/0036-r1-module-decisions.md) §9 (a guard-free v1 of `inspection_standard`; INSPECTIONS-02/03 publish later versions)
4. Lifecycle source: [`inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) ("Features" first bullet and "Decisions and notes")
5. The installer this builds on: `aip/modules/approvals/presets.py` and `DefinitionsService.install_preset` (APPROVALS-08)

> **Owner confirmation.** The AIP source (TASKS 8.2, spec E4-S3/S4, PRD §7.3 and the AIP lifecycle
> tests) is **not in this repo** ([OPEN-QUESTIONS.md](../OPEN-QUESTIONS.md) #4). The golden cases are
> **provisional**, derived only from the blueprint lifecycle line
> "draft > assignable > assigned > in progress > inspector review > supervisor review > [client review]
> > completed; reject/resend; re-inspect". The cases file carries `confirmedBy: null`, and the test run
> prints a `PROVISIONAL golden cases — owner confirmation pending` warning until the owner fills it in.
> A reviewer who finds a lifecycle that differs from AIP changes only the JSON presets and the golden
> cases, never engine code.

## Spec (Python, per ADR 0001)

Ship the inspection review chain as data: two presets (standard, and with client review), neutral state
and action codes, en-AU term keys, and golden lifecycle tests that run through both the pure evaluator and
the real `TransitionService` on Postgres.

- **files**:
  - `config/workflows/inspection_standard.json`, `config/workflows/inspection_client_review.json`
    (APPROVALS-08 preset keys are snake_case file stems, so `inspection.standard` becomes `inspection_standard`)
  - `config/terms/en-AU/approvals.json` (`workflow.inspection.state.*` and `workflow.inspection.action.*`)
  - `apps/api/aip/modules/approvals/presets.py` (`list_presets`, `validate_presets`)
  - `apps/api/aip/modules/approvals/schemas.py` (`requiresComment`; preset HTTP models)
  - `apps/api/aip/modules/approvals/transition.py` (422 `COMMENT_REQUIRED`)
  - `apps/api/aip/modules/approvals/routes.py` (`GET /presets`, `POST /definitions/from-preset`)
  - `apps/api/aip/modules/approvals/seeds.py` (`kaefer-demo` gets `inspection_standard`)
  - `apps/api/aip/modules/approvals/manifest.toml` (`approvals.inspection.*` permissions)
  - `apps/api/aip/main.py` (validate every preset at boot)
  - `apps/api/aip/modules/approvals/tests/golden/inspection_lifecycle_cases.json`
  - `apps/api/aip/modules/approvals/tests/test_inspection_golden.py` (evaluator, no database)
  - `apps/api/aip/modules/approvals/tests/test_inspection_preset_db.py` (TransitionService on Postgres)
  - Image and compose: `config/workflows` copied into the API image; an `approvals-seed` one-shot
- **steps**:
  1. Both presets are valid `WorkflowDefinitionSpec`s with `recordType: "inspection"`.
     - States: `draft` (initial), `assignable`, `assigned`, `in_progress`, `inspector_review`,
       `supervisor_review`, `client_review` (client-review variant only), `rejected`, `completed` (terminal).
     - Standard transitions: `ready` draft→assignable; `assign` assignable→assigned; `unassign`
       assigned→assignable; `start` assigned→in_progress; `submit` in_progress→inspector_review;
       `review_pass` inspector_review→supervisor_review; `approve` supervisor_review→completed (critical,
       `signoffAction: inspection.approve`); `reject` from inspector_review or supervisor_review →rejected
       (`requiresComment`); `resend` rejected→assigned.
     - Client-review variant: `approve` goes supervisor_review→client_review (not critical);
       `client_approve` client_review→completed (critical, `signoffAction: inspection.client_approve`);
       `reject` client_review→rejected.
     - Re-inspect is **not** a transition: `completed` is terminal, and a re-inspection is a new
       inspection and instance created by INSPECTIONS-01.
     - `requiresComment` is a new optional transition field (default false). `transition()` refuses a
       missing or blank comment with **422** `COMMENT_REQUIRED` (ADR 0035 §7: validation errors are 422,
       not the spec's 400). `availableTransitions` exposes `requiresComment` so a client can ask for one.
  2. Client review is chosen **per project** by installing `inspection_client_review` with a
     `projectId`. Definition resolution prefers the project's definition, then the tenant-wide one
     (APPROVALS-01), so the variant must only ever be installed project-scoped. No guards (ADR 0036 §9).
  3. Permissions in `approvals/manifest.toml`: `approvals.inspection.assign` (ready, assign, unassign,
     resend), `approvals.inspection.execute` (start, submit), `approvals.inspection.review` (review_pass,
     reject at inspector_review), `approvals.inspection.approve` (approve, reject at supervisor_review),
     `approvals.inspection.client_approve` (client_approve, reject at client_review). INSPECTIONS tasks
     may move them to the inspections manifest.
  4. Terms: `workflow.inspection.state.<code>` and `workflow.inspection.action.<code>` in
     `config/terms/en-AU/approvals.json`. The presets hold only codes and keys.
  5. Presets:
     - `list_presets()` reads every `config/workflows/*.json` and validates it with `validate_spec`;
       `create_app` calls `validate_presets()` when approvals is loaded, so a bad preset stops startup.
     - `install_preset` is APPROVALS-08's (idempotent: an unchanged preset is a no-op). The definition
       key is the preset key.
     - `GET /api/v1/approvals/presets` (`approvals.view`) lists `{key, recordType, states, actions}`;
       `POST /api/v1/approvals/definitions/from-preset {presetKey, projectId?}` (`approvals.design`)
       installs one and returns `{id, key, recordType, projectId, version, status}`; 404
       `PRESET_NOT_FOUND` for an unknown key.
     - `python -m aip.modules.approvals.seeds` installs `inspection_standard` in `kaefer-demo`
       (development, test and demo only; idempotent).
  6. Golden cases: `inspection_lifecycle_cases.json` has a header `{"source": "blueprint
     (provisional)", "confirmedBy": null, "confirmedOn": null}` and `cases: [{name, variant, start,
     actions[], expect: {state} | {error} | {available}}]`. Every case runs through the evaluator and
     through `TransitionService` on Postgres. While `confirmedBy` is null the run warns
     `PROVISIONAL golden cases — owner confirmation pending`.
- **acceptance**:
  - Both presets load and validate at boot, and every state and action has an en-AU term key.
  - Every golden case passes through both the evaluator and the transition service.
  - `approve` (standard) and `client_approve` need sign-off assurance (critical).
  - Projects with the client-review variant go through `client_review`; the others do not.
  - The PR states that the cases are provisional (blueprint-derived) and not yet confirmed by the owner.
- **tests**:
  - **unit** (`test_inspection_golden.py`): both presets parse with `validate_spec` and every state is
    reachable; every `labelKey` is in the en-AU dictionary; all golden cases (`standard-happy-path`,
    `client-happy-path`, `approve-too-early`, `reject-and-resend`, `client-cannot-skip`, `unassign`,
    `completed-is-final`, plus reject-from-client-review and unknown-action cases) through the evaluator.
  - **integration** (`test_inspection_preset_db.py`, Testcontainers Postgres):
    - every golden case through `TransitionService` as a user holding every inspection permission;
    - `standard-happy-path` with separate supervisor (assign, approve, fresh aal2), inspector (execute)
      and lead inspector (review): every step 200, **6** history rows (the original spec's 7 counted one
      too many: there are six transitions), `chainValid` true;
    - the inspector attempts `approve` at `supervisor_review` → 403;
    - the supervisor attempts `approve` with a stale aal2 session → 401 `STEP_UP_REQUIRED` (ADR 0034);
    - `reject` without a comment → 422 `COMMENT_REQUIRED`, nothing written;
    - `inspection_client_review` installed for project RT-01 only: an RT-01 instance reaches
      `client_review` after `approve`, a KF-01 instance reaches `completed`;
    - installing a preset twice → 1 active definition, version 1;
    - the routes: `GET /presets` lists both, `POST /definitions/from-preset` installs and is idempotent,
      needs `approvals.design` (403) and 404s an unknown preset; a new instance starts at `draft` with
      `availableTransitions[0].labelKey == "workflow.inspection.action.ready"`;
    - the seed installs `inspection_standard` in `kaefer-demo` and refuses in production.
  - **e2e**: carried to TESTING-13, which already seeds a demo workflow and runs the approvals
    journeys in `e2e-skeleton` (the same carry-over APPROVALS-02 made to APPROVALS-07).
