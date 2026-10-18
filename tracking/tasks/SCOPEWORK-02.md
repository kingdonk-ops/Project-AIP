# SCOPEWORK-02 — Completion gate: requirement evaluation, stored gate evaluations, completed_at only on pass

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`scope_work`](../../docs/blueprint/modules/scope_work/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-01, SCOPEWORK-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/scope_work/README.md`](../../docs/blueprint/modules/scope_work/README.md) ("Progress roll-up ... and hard completion gate", "Gate logic lives only in gate.py") and, for columns only, [`data-model.md`](../../docs/blueprint/modules/scope_work/data-model.md) (`rsw_gate_evaluations`)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (append-only tables and grants), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) and [0030](../../docs/adr/0030-outbox-dispatch-semantics.md) (outbox, idempotent subscribers), [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules), [0021](../../docs/adr/0021-retention-schedule.md) (evidence is kept, never edited), [0025](../../docs/adr/0025-time-and-timezones.md) (UTC), [0027](../../docs/adr/0027-default-role-permission-expansion.md) (permission verbs), [0036](../../docs/adr/0036-r1-module-decisions.md)
4. The inspections published interface built by INSPECTIONS-01 (`apps/api/aip/modules/inspections/api.py`: `InspectionsApi.get_state`, event `inspection.state_changed` v1), and [`inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) for what "accepted" means
5. Platform: `apps/api/aip/platform/events/subscribers.py` (`@subscriber`, idempotent on `event.id`), `apps/api/aip/platform/db/concurrency.py`, `db/templates/append_only_table.sql.tpl`

> Out of scope: creating the linked inspection or ITP and the hold-point link (SCOPEWORK-03; this task reads the
> link columns SCOPEWORK-01 created, and its tests fill them directly), pages (SCOPEWORK-04), RFI and consumables
> requirements (no RFI or stock module in R1, see step 2), reopening a completed RSW, notifications.

## Spec

Put the RSW completion gate in one place (`gate.py`): evaluate every task requirement from inspection state read through `InspectionsApi`, store each evaluation as append-only evidence, cache the progress roll-up, and set `completed_at` only when the gate passes (tag: extend).

- **files**:
  - apps/api/aip/modules/scope_work/gate.py
  - apps/api/aip/modules/scope_work/tables.py
  - apps/api/aip/modules/scope_work/schemas.py
  - apps/api/aip/modules/scope_work/repository.py
  - apps/api/aip/modules/scope_work/service.py
  - apps/api/aip/modules/scope_work/events.py
  - apps/api/aip/modules/scope_work/routes.py
  - apps/api/aip/modules/scope_work/api.py
  - apps/api/aip/modules/scope_work/manifest.toml
  - apps/api/aip/modules/scope_work/tests/test_gate_unit.py
  - apps/api/aip/modules/scope_work/tests/test_gate_db.py
  - apps/api/migrations/versions/<timestamp>_scope_work_gate_evaluations.py
  - config/terms/en-AU/scope_work.json
- **steps**:
  - 1. Migration `<timestamp>_scope_work_gate_evaluations.py`:
    - (a) create `rsw_gate_evaluations` with `render_template("append_only_table", table="rsw_gate_evaluations", columns=..., partition_column="created_at")` and register it in the same revision with `INSERT INTO partition_settings (table_name) VALUES ('rsw_gate_evaluations')`. Columns: `rsw_id uuid NOT NULL`, `asset_id uuid NOT NULL`, `project_id uuid NOT NULL`, `trigger text NOT NULL` (`CHECK (trigger IN ('evaluate','complete','event'))`), `passed boolean NOT NULL`, `progress_pct numeric(5,2) NOT NULL`, `requirements jsonb NOT NULL` (every requirement with its outcome), `blockers jsonb NOT NULL` (the unmet ones), `rsw_sync_version integer NOT NULL`, `actor_user_id uuid NULL` (null for `event`), `source_event_id uuid NULL`. Index `(tenant_id, rsw_id, created_at DESC)` and `(tenant_id, source_event_id) WHERE source_event_id IS NOT NULL`. The template revokes `UPDATE, DELETE, TRUNCATE` from `aip_app`.
    - (b) On `scope_tasks` (created in SCOPEWORK-01) add indexes `(tenant_id, inspection_id) WHERE inspection_id IS NOT NULL AND deleted_at IS NULL` and `(tenant_id, itp_id) WHERE itp_id IS NOT NULL AND deleted_at IS NULL`, so the subscriber in step 6 finds affected tasks.
  - 2. `gate.py` is the **only** place gate rules live. Nothing else in the codebase decides whether an RSW may complete.
    - `ACCEPTED_INSPECTION_STATES = frozenset({"completed"})`: the terminal state of the APPROVALS-05 `inspection` preset. A `rejected` or any other state is not accepted.
    - Pure function `evaluate(tasks: Sequence[TaskFacts]) -> GateResult`. `TaskFacts` is `{task_id, task_name, discipline_key, status, requires_itp, requires_inspection, requires_rfi, requires_consumables, inspection_id, inspection_state, itp_id, itp_state, hold_point_id, hold_point_released}`. Tasks with `status = 'cancelled'` are skipped. For each remaining task, one requirement per true flag:
      - `inspection`: `inspection_id` null → blocker `inspection_missing`; state not accepted → `inspection_not_accepted` (with `state`); else `accepted`.
      - `itp`: `itp_id` null → `itp_missing`; ITP state not accepted → `itp_not_accepted`; `hold_point_id` set and `hold_point_released` false → `hold_point_not_released`; else `accepted`.
      - `rfi` and `consumables`: outcome `not_applicable` with reason `no_rfi_module` / `no_stock_module`. **Decision:** the flags are kept (SCOPEWORK-01 stores them and the AIP import carries them), but the gate treats them as not applicable and never blocks on them until an RFI or stock module exists; the stored evaluation records them so the change is visible later.
    - `GateResult = {passed, progress_pct, requirements[], blockers[]}`. `progress_pct` = accepted ÷ applicable requirements × 100, rounded half-up to 2 places; with live tasks but no applicable requirements it is `100`. With no live (non-cancelled) tasks the gate fails with the single blocker `{code: "no_tasks"}` and `progress_pct` 0.
    - Blocker shape: `{taskId, taskName, disciplineKey, requirement, code, state?}`, sorted by discipline sequence, task sequence, then requirement (`inspection`, `itp`).
    - `async collect_facts(conn, rsw_id) -> list[TaskFacts]` reads the live tasks (SCOPEWORK-01 repository) and fills inspection facts **only** through `aip.modules.inspections.api.InspectionsApi().get_state(conn, inspection_id)`. A `NotFoundError` (deleted or another tenant's inspection) counts as missing (`inspection_missing` / `itp_missing`), never as accepted. In this task `collect_facts` leaves `hold_point_released` as `None`, and `evaluate` treats a set `hold_point_id` with `None` as not released (fail closed). SCOPEWORK-03, which depends on INSPECTIONS-03, fills it from `InspectionsApi().is_step_released(conn, hold_point_id)`; until then no route writes `hold_point_id`. No query touches an inspections table.
  - 3. `service.py` `GateService`, inside the request's `with_tenant` transaction:
    - (a) `evaluate_and_store(conn, actor, rsw_id, trigger)`: `SELECT ... FOR UPDATE` the RSW, `collect_facts`, `evaluate`, insert one `rsw_gate_evaluations` row (UUIDv7 id), and set the cached `rsws.progress_pct` with a plain `UPDATE rsws SET progress_pct = ..., updated_at = now()` that does **not** bump `sync_version` (a derived cache must not make a user's next edit conflict). Returns the stored evaluation.
    - (b) `complete(conn, actor, rsw_id, expected_sync_version)`: RSW must be `in_progress`, else 409 `RSW_NOT_IN_PROGRESS` and nothing stored. Run (a) with trigger `complete`. On pass, `update_with_version(conn, rsws, rsw_id, expected_sync_version, {"status": "completed", "completed_at": now()})` (stale → 409 `SYNC_VERSION_CONFLICT`, and the whole transaction, evaluation included, rolls back) and `emit(conn, "rsw.completed", 1, Aggregate("rsw", rsw_id), {rswId, projectId, assetId, evaluationId, completedAt}, asset_id=asset_id)`. On fail, commit the evaluation and the progress cache, then answer 422 `GATE_FAILED` with `{evaluationId, progressPct, blockers}`; the service returns the failure as a value and the route turns it into the 422 **after** the transaction commits, so the failed evaluation is kept for audit while `status` and `completed_at` are untouched.
    - (c) `completed_at` is written nowhere else: grep-able test in step 7.
  - 4. Routes (all with `requires(...)` and `Resource(project_id=rsw.project_id)`):
    - `POST /api/v1/rsws/{id}/gate-evaluations` (`rsw.update`) → 201 with the stored evaluation (trigger `evaluate`). An explicit POST, because every evaluation is stored and a GET must not write.
    - `GET /api/v1/rsws/{id}/gate-evaluations?limit=` (`rsw.view`) → newest first, limit ≤ 100.
    - `POST /api/v1/rsws/{id}/complete {expectedSyncVersion}` (`rsw.approve`) → 200 with the RSW (`status:'completed'`) and `evaluationId`, or 422 `GATE_FAILED` as above.
    - `GET /api/v1/rsws/{id}` (SCOPEWORK-01) gains `latestGate: {evaluationId, passed, createdAt, blockerCount} | null`.
  - 5. Manifest: add permission `rsw.approve` ("Complete an RSW through the completion gate"; the ADR 0027 `approve` verb, so supervisor-level default roles get it), event `rsw.completed` v1, and `[[subscribes]] name = "inspection.state_changed" version = 1`. Payload model for `rsw.completed` in `events.py`.
  - 6. Subscriber in `events.py`: `@subscriber("inspection.state_changed", 1)` refreshes the progress roll-up. It finds live tasks whose `inspection_id` or `itp_id` is `payload.inspectionId`, and for each distinct RSW in `in_progress` calls `evaluate_and_store(..., trigger="event")` with `actor_user_id` null and `source_event_id = event.id`. It is idempotent on `event.id`: if an evaluation with that `source_event_id` and `rsw_id` exists it does nothing. It never completes an RSW (completion is a signed user action) and never commits `conn`.
  - 7. `ScopeWorkApi` (`api.py`) adds `get_latest_gate(conn, rsw_id) -> GateEvaluationOut | None` for SCOPEWORK-04 and report templates.
  - 8. Terms: `scope_work.gate.passed`, `scope_work.gate.failed`, `scope_work.gate.blocker.<inspection_missing|inspection_not_accepted|itp_missing|itp_not_accepted|hold_point_not_released|no_tasks>`, `scope_work.gate.not_applicable.<no_rfi_module|no_stock_module>`, `scope_work.error.<GATE_FAILED|RSW_NOT_IN_PROGRESS>`.
- **acceptance**:
  - Gate rules exist only in `gate.py`; a test fails if any other module file assigns `completed_at` or the `completed` status.
  - Every evaluation, passed or failed, leaves exactly one `rsw_gate_evaluations` row; the table cannot be updated or deleted by `aip_app`.
  - An RSW reaches `completed` with `completed_at` set only in the same transaction as a passing evaluation and one `rsw.completed` event.
  - The gate reads inspection state only through `InspectionsApi`; `scope_work` imports nothing from `aip.modules.inspections` except `api`.
  - RFI and consumable flags never block the gate in R1 and are recorded as `not_applicable`.
- **tests**:
  - **unit** (`test_gate_unit.py`, pure `evaluate`):
    - One task, `requires_inspection`, state `completed` → `passed: true`, `progress_pct: 100`, blockers `[]`.
    - Same with state `in_progress` → `passed: false`, one blocker `{code:'inspection_not_accepted', state:'in_progress'}`, `progress_pct: 0`.
    - `requires_inspection` with `inspection_id` null → blocker `inspection_missing`.
    - Three tasks: inspection accepted; ITP `completed` with `hold_point_id` set and `hold_point_released: false`; inspection `rejected` → `passed: false`, 2 blockers (`hold_point_not_released`, `inspection_not_accepted`), `progress_pct: 33.33`.
    - A task with only `requires_rfi` and `requires_consumables` → `passed: true`, `progress_pct: 100`, two requirements with outcome `not_applicable`.
    - The only task `cancelled` → `passed: false`, blockers `[{code:'no_tasks'}]`. No tasks → the same.
    - A task with no flags → `passed: true`, `progress_pct: 100`.
    - Blockers come out sorted by discipline sequence then task sequence whatever the input order.
    - Source scan: no file under `apps/api/aip/modules/scope_work/` other than `service.py`'s `complete` writes `completed_at`; no file imports `aip.modules.inspections` other than via `.api`.
  - **integration** (testcontainers-python, `kaefer-demo` and `tenant-b`; inspections created with `InspectionsApi.create_inspection` and driven through the `inspection` preset actions with `ApprovalsApi.transition`; task link columns set as superuser because SCOPEWORK-03 is not merged):
    - RSW `in_progress` with one task requiring an inspection that is `in_progress`: `POST /rsws/{id}/complete {expectedSyncVersion: 2}` → 422 `GATE_FAILED`, `blockers[0].code = 'inspection_not_accepted'`; `SELECT count(*) FROM rsw_gate_evaluations WHERE rsw_id = ...` → 1 with `passed = false`; RSW `status` still `in_progress`, `completed_at` null, `sync_version` still 2.
    - Drive the inspection to `completed`, complete again → 200, `status:'completed'`, `completedAt` set; 2 `rsw_gate_evaluations` rows (the second `passed = true`, trigger `complete`); `SELECT count(*) FROM domain_events WHERE event_name = 'rsw.completed'` → 1.
    - `POST /complete` on a `draft` RSW → 409 `RSW_NOT_IN_PROGRESS`, 0 new `rsw_gate_evaluations` rows.
    - Passing gate with a stale `expectedSyncVersion` → 409 `SYNC_VERSION_CONFLICT`, no new `rsw_gate_evaluations` row and no `rsw.completed` event.
    - `POST /gate-evaluations` → 201, `progressPct` matches, `rsws.progress_pct` updated and `sync_version` unchanged.
    - Dispatch an `inspection.state_changed` event for the linked inspection → one `rsw_gate_evaluations` row with trigger `event` and `source_event_id` set; dispatch the same event again → still one; the RSW is not completed.
    - A task whose `inspection_id` is a `tenant-b` inspection id → blocker `inspection_missing` (never accepted).
    - A user with `rsw.update` but not `rsw.approve` → `POST /complete` 403, nothing written. A `tenant-b` user → `POST /api/v1/rsws/{kaefer id}/gate-evaluations` 404 and `GET .../gate-evaluations` 404.
    - As `aip_app`: `UPDATE rsw_gate_evaluations SET passed = true` → `permission denied`; `DELETE FROM rsw_gate_evaluations` → `permission denied`.
    - Make `emit` raise during a passing complete → 500; the RSW is still `in_progress` and no `rsw_gate_evaluations` row was added.
  - **e2e**:
    - Covered by the integration tests above (real app over HTTP, real Postgres, real inspections and approvals modules): this row has no page and the repo has no Playwright API project yet. The browser journey (gate status and blockers on the RSW detail page, cross-tenant 404, axe) ships with SCOPEWORK-04, and the CUI golden scenarios with SCOPEWORK-05.
