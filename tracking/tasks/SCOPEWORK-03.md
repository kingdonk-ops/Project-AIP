# SCOPEWORK-03 — Auto-create the linked ITP or inspection from task flags, one hold-point link per task

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`scope_work`](../../docs/blueprint/modules/scope_work/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-03, SCOPEWORK-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/scope_work/README.md`](../../docs/blueprint/modules/scope_work/README.md) ("Auto-create linked ITP/RFI/inspection from task flags; unique hold-point link per task")
3. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) (ITPs and hold points), then the inspections published interface built by INSPECTIONS-01 and INSPECTIONS-03 (`apps/api/aip/modules/inspections/api.py`: `InspectionsApi.create_inspection`, `get_itp_step`, `is_step_released`)
4. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction), [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules), [0035](../../docs/adr/0035-transition-service-implementation.md) (how `Actor` and the policy service are passed to another module's api), [0036](../../docs/adr/0036-r1-module-decisions.md)
5. The SCOPEWORK-01 and SCOPEWORK-02 code: `apps/api/aip/modules/scope_work/service.py`, `gate.py`

> Out of scope: RFI creation (no RFI module in R1; `requires_rfi` stays a flag the gate treats as not applicable,
> SCOPEWORK-02), consumable issuance (no stock module), RSW templates that generate tasks and ITPs, pages
> (SCOPEWORK-04), deleting or cancelling a linked inspection when a flag is cleared.

## Spec

Create the inspection or ITP a scope task's flags require through `InspectionsApi.create_inspection`, store the link on the task, let a user link exactly one ITP hold point per task, and make the completion gate check that hold point's release (tag: extend).

- **files**:
  - apps/api/aip/modules/scope_work/linking.py
  - apps/api/aip/modules/scope_work/gate.py
  - apps/api/aip/modules/scope_work/service.py
  - apps/api/aip/modules/scope_work/repository.py
  - apps/api/aip/modules/scope_work/schemas.py
  - apps/api/aip/modules/scope_work/routes.py
  - apps/api/aip/modules/scope_work/events.py
  - apps/api/aip/modules/scope_work/manifest.toml
  - apps/api/aip/modules/scope_work/tests/test_linking_unit.py
  - apps/api/aip/modules/scope_work/tests/test_linking_db.py
  - config/terms/en-AU/scope_work.json
- **steps**:
  - 1. No migration: SCOPEWORK-01 created `scope_tasks.inspection_id`, `itp_id`, `hold_point_id`, `inspection_template_id`, `itp_template_id` and the unique `(tenant_id, hold_point_id)` index.
  - 2. `linking.py` `plan_links(rsw, tasks, discipline_defaults) -> LinkPlan` (pure): for each live task that is not `cancelled`, on an RSW in `in_progress`:
    - `requires_inspection` and `inspection_id` null → create with `kind="inspection"` and template `task.inspection_template_id`, else the discipline's `scope_vocabularies.config.defaultInspectionTemplateId`.
    - `requires_itp` and `itp_id` null → create with `kind="itp"` and template `task.itp_template_id`, else `config.defaultItpTemplateId`.
    - No template from either place → `skipped` with reason `no_template` (the gate then reports `inspection_missing` / `itp_missing`).
    - Asset: `task.component_asset_id`, else `rsw.asset_id`. Project: `rsw.project_id`.
    - A task whose flag is cleared keeps its link (the inspection is evidence and is not deleted); a task re-flagged with a link already set gets nothing new.
  - 3. `service.py` `LinkService.ensure_links(conn, policy, actor, rsw_id)`, inside the caller's `with_tenant` transaction:
    - (a) `SELECT ... FOR UPDATE` the RSW and its live tasks (ordered by id, so two callers lock in the same order), load discipline defaults, `plan_links`.
    - (b) For each planned create call `aip.modules.inspections.api.InspectionsApi().create_inspection(conn, policy, actor, asset_id=..., project_id=..., template_id=..., kind=..., source={"recordType": "scope_task", "recordId": task_id})`. That call checks the inspections module's own create permission for `actor`; a 403 or a template error from it rolls back the whole request (no partial links). A template error → 422 `TEMPLATE_INVALID` with `{taskId, requirement}`.
    - (c) Write the returned id to `inspection_id` or `itp_id` with a plain `UPDATE scope_tasks ... WHERE id = ? AND <column> IS NULL` (a link is set once), bump the task's `sync_version`, and `emit(conn, "rsw.requirement_linked", 1, Aggregate("rsw", rsw_id), {rswId, taskId, requirement, inspectionId}, asset_id=asset_id)`.
    - (d) Return `{created: [{taskId, requirement, inspectionId}], skipped: [{taskId, requirement, reason}]}`.
  - 4. Call sites, each in the same transaction as the triggering write:
    - `POST /rsws/{id}/start` (SCOPEWORK-01) runs `ensure_links` after the status change; the response gains `links`.
    - Task create and `PATCH /scope-tasks/{id}` on an `in_progress` RSW run `ensure_links` for that RSW.
    - `POST /api/v1/rsws/{id}/linked-records` (`rsw.update`) runs it on demand and is idempotent: a second call creates nothing. A `draft`, `completed` or `cancelled` RSW → 409 `RSW_NOT_IN_PROGRESS`.
  - 5. Hold-point link, one per task:
    - `PUT /api/v1/scope-tasks/{id}/hold-point {itpStepId, expectedSyncVersion}` (`rsw.update`). The task must have `itp_id`, else 409 `ITP_NOT_LINKED`. `InspectionsApi().get_itp_step(conn, itp_step_id)` → `None` (missing or another tenant's) → 422 `HOLD_POINT_NOT_FOUND`; a step not on the task's ITP (`step.inspection_id != task.itp_id`) → 422 `HOLD_POINT_WRONG_ITP`; a step that is not a hold point → 422 `NOT_A_HOLD_POINT`. Write with `update_with_version`; the unique `(tenant_id, hold_point_id)` index violation (`UniqueViolation`) → 409 `HOLD_POINT_ALREADY_LINKED` with the other task's id.
    - `DELETE /api/v1/scope-tasks/{id}/hold-point?expectedSyncVersion=` clears it. Both are refused on a `completed` or `cancelled` RSW (409 `RSW_CLOSED`).
  - 6. Gate: in `gate.collect_facts` fill `hold_point_released` with `InspectionsApi().is_step_released(conn, hold_point_id)` for tasks with a hold point. `evaluate` is unchanged (it already blocks with `hold_point_not_released` when the value is not `True`).
  - 7. Manifest: event `rsw.requirement_linked` v1 (payload model in `events.py`). Terms: `scope_work.link.created`, `scope_work.link.skipped.no_template`, `scope_work.error.<TEMPLATE_INVALID|ITP_NOT_LINKED|HOLD_POINT_NOT_FOUND|HOLD_POINT_WRONG_ITP|NOT_A_HOLD_POINT|HOLD_POINT_ALREADY_LINKED>`.
- **acceptance**:
  - Starting an RSW creates exactly one inspection per `requires_inspection` task and one ITP per `requires_itp` task that has a template, in one transaction with one `rsw.requirement_linked` event each; repeating any trigger creates nothing more.
  - All inspections are created through `InspectionsApi.create_inspection`; `scope_work` reads and writes no inspections table.
  - A hold point is linked to at most one task in a tenant, and only a hold point of that task's own ITP.
  - The gate blocks an RSW whose linked hold point is not released.
- **tests**:
  - **unit** (`plan_links`):
    - `in_progress` RSW, task `{requires_inspection: true, inspection_id: null, inspection_template_id: T1}` → one create `{kind:'inspection', template_id: T1, asset_id: rsw.asset_id}`.
    - Same task with `component_asset_id: C1` → create with `asset_id: C1`.
    - Task `{requires_itp: true, itp_template_id: null}` with discipline config `{"defaultItpTemplateId": T2}` → create `{kind:'itp', template_id: T2}`; with no discipline default → `skipped [{requirement:'itp', reason:'no_template'}]`.
    - Task with `inspection_id` already set → no create. Task `cancelled` → nothing. RSW `draft` → empty plan.
    - Task with both flags and both templates → two creates, `inspection` first.
    - `evaluate` with a task `{requires_itp, itp_state:'completed', hold_point_id: H1, hold_point_released: true}` → passed; with `hold_point_released: false` → blocker `hold_point_not_released`.
  - **integration** (testcontainers-python, `kaefer-demo` and `tenant-b`, published form templates from the FORMS-01 fixtures, the `inspection` preset installed):
    - RSW with discipline `coating`, tasks `test` (`requires_inspection`, template T1) and `coat` (`requires_itp`, template T2), plus `blast` (no flags). `POST /rsws/{id}/start` → 200, `links.created` has 2 entries; `InspectionsApi.get_inspection` for each returns `kind` `inspection` / `itp`, the RSW's `project_id`, `source.recordId` = the task id; the `scope_tasks` row for `test` has `inspection_id` set; `SELECT count(*) FROM domain_events WHERE event_name = 'rsw.requirement_linked'` → 2.
    - `POST /rsws/{id}/linked-records` → 200 `{created: [], skipped: []}`; still 2 events.
    - Two concurrent `POST /linked-records` after adding a new flagged task (`asyncio.gather`) → exactly one inspection created for it.
    - A user with `rsw.update` but without the inspections create permission starts the RSW → 403; the RSW is still `draft` and no task has a link.
    - A task with `requires_itp` and no template anywhere → `skipped [{reason:'no_template'}]`, and `POST /gate-evaluations` lists blocker `itp_missing` for it.
    - `PUT /scope-tasks/{coat}/hold-point {itpStepId: <hold step of coat's ITP>}` → 200; the same step on another task with an ITP → 409 `HOLD_POINT_ALREADY_LINKED`; a hold step of a different ITP → 422 `HOLD_POINT_WRONG_ITP`; a witness step → 422 `NOT_A_HOLD_POINT`; a `tenant-b` step id → 422 `HOLD_POINT_NOT_FOUND`; on task `test` (no ITP) → 409 `ITP_NOT_LINKED`.
    - With the hold point linked and not released, `POST /rsws/{id}/complete` → 422 `GATE_FAILED` with blocker `hold_point_not_released`; after the hold point is released through the INSPECTIONS-03 sign-off and both inspections reach `completed`, complete → 200.
    - A `tenant-b` user: `POST /api/v1/rsws/{kaefer id}/linked-records` → 404; `PUT /api/v1/scope-tasks/{kaefer task}/hold-point` → 404.
    - Make `emit` raise on the second link → 500; neither task has a link and no inspection was created.
  - **e2e**:
    - Covered by the integration tests above (real app, real Postgres, real inspections and approvals modules): this row has no page and the repo has no Playwright API project yet. The browser journey with linked inspections on the RSW detail page ships with SCOPEWORK-04; hold-point scenarios on CUI data are INSPECTIONS-06 and SCOPEWORK-05.
