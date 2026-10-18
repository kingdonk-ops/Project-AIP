# INSPECTIONS-01 — Inspections against an asset with a pinned form revision, lifecycle on the APPROVALS-05 preset

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | APPROVALS-05, ASSETS-01, FORMS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/inspections/README.md`](../../docs/blueprint/modules/inspections/README.md) ("Features" first bullet, "Data") and [`data-model.md`](../../docs/blueprint/modules/inspections/data-model.md) (notes only; the `inspections` columns are listed below)
3. [APPROVALS-05](APPROVALS-05.md): the preset's definition key `inspection`, its state and action codes and its `approvals.inspection.*` permissions
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (Core + raw-SQL Alembic, `with_tenant`), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction), [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0025](../../docs/adr/0025-time-and-timezones.md) (UTC storage), [0035](../../docs/adr/0035-transition-service-implementation.md) (record resolver, guard facts provider, 401 `STEP_UP_REQUIRED`), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 decisions)
5. Code to build on: `apps/api/aip/modules/projects/` (module pattern, `tests/conftest.py`), `apps/api/aip/modules/approvals/api.py`, `apps/api/aip/modules/approvals/guards/context_providers.py`, `apps/api/migrations/versions/202610181200_approvals_decision_history.py`, `db/templates/tenant_table.sql.tpl`

## Spec

Create the `inspections` module: an inspection is filled in against one asset from one pinned, published form revision, and its lifecycle is a workflow instance of the APPROVALS-05 `inspection` definition driven through `ApprovalsApi` (tag: extend).

- **files**:
  - apps/api/aip/modules/inspections/__init__.py
  - apps/api/aip/modules/inspections/manifest.toml
  - apps/api/aip/modules/inspections/tables.py
  - apps/api/aip/modules/inspections/schemas.py
  - apps/api/aip/modules/inspections/repository.py
  - apps/api/aip/modules/inspections/service.py
  - apps/api/aip/modules/inspections/workflow.py
  - apps/api/aip/modules/inspections/policies.py
  - apps/api/aip/modules/inspections/events.py
  - apps/api/aip/modules/inspections/routes.py
  - apps/api/aip/modules/inspections/api.py
  - apps/api/aip/modules/inspections/tests/__init__.py
  - apps/api/aip/modules/inspections/tests/conftest.py
  - apps/api/aip/modules/inspections/tests/test_unit.py
  - apps/api/aip/modules/inspections/tests/test_inspections_db.py
  - apps/api/migrations/versions/<timestamp>_inspections_core.py
  - config/terms/en-AU/inspections.json
- **steps**:
  - 1. Scaffold with `python tools/new_module.py inspections`. `manifest.toml`: `id = "inspections"`, `depends_on = ["approvals", "assets", "forms", "projects", "access", "identity", "tenancy"]`, `permission_namespaces = ["inspection"]`, permissions `inspection.view` ("View inspections") and `inspection.create` ("Create inspections and re-inspections"). Lifecycle permissions stay the `approvals.inspection.*` codes APPROVALS-05 declared; this task does not move them.
  - 2. Migration `<timestamp>_inspections_core.py` renders `render_template("tenant_table", table="inspections", sync=True, columns=...)` (`aip.platform.db.templates`) and so creates `inspections` with these own columns:
    - `asset_id uuid NOT NULL`, `project_id uuid NULL`, `template_id uuid NOT NULL`, `template_revision_id uuid NOT NULL` (pinned at creation, never changed);
    - `kind text NOT NULL` with `CHECK (kind IN ('inspection', 'itp', 'rfi'))` (the `inspection.kind.*` term keys already in `config/terms/en-AU/inspections.json`);
    - `source text NOT NULL` with `CHECK (source IN ('manual', 'scope_task', 'reinspection', 'import'))` and `source_ref_id uuid NULL` (the scope task, or the inspection being re-inspected; required when `source` is `scope_task` or `reinspection`, a CHECK);
    - `itp_parent_id uuid NULL` (an ITP step's child inspection, used by INSPECTIONS-03 and later);
    - `workflow_instance_id uuid NOT NULL`, `state text NOT NULL` (a cache of the instance's `current_state` for registers; the instance is the truth);
    - `created_by uuid NOT NULL`.

    Add `CONSTRAINT uq_inspections_id_tenant_id UNIQUE (id, tenant_id)` (so later inspections tables reference an inspection in their own tenant), `FOREIGN KEY (tenant_id) REFERENCES tenants (id)`, and indexes `(tenant_id, asset_id)`, `(tenant_id, project_id, state)`, `(tenant_id, template_revision_id)` and a unique `(tenant_id, workflow_instance_id)`. `itp_parent_id` and `source_ref_id` stay plain uuids (checked by the service). No foreign keys to other modules' tables: existence is checked through their `api.py`. The template supplies FORCE RLS, the fail-closed policy, `sync_version`, `client_generated_id` and the `aip_app` grants.
  - 3. `tables.py` declares the Core `Table`; `repository.py` holds every query (`insert_inspection`, `get_inspection`, `lock_inspection` with `FOR UPDATE`, `list_inspections` with filters `asset_id`, `project_id`, `state`, `kind` and keyset paging on `(created_at, id)` like projects, `set_state`). Ids are UUIDv7 from the app.
  - 4. `service.py` `InspectionService.create(conn, policy, actor, data)` in one `with_tenant` transaction:
    - (a) `policy.assert_can(principal, "inspection.create", Resource(project))`; deny → 403 and nothing written.
    - (b) `AssetsApi.assert_asset_exists(conn, asset_id)` → 404 `ASSET_NOT_FOUND` when missing or another tenant's; `ProjectsApi.assert_project_exists(conn, project_id)` when a project is given → 404.
    - (c) `FormsApi.get_current_revision(conn, template_id)`; no published revision → 422 `TEMPLATE_NOT_PUBLISHED`. Store its id as `template_revision_id`. A body may name `templateRevisionId` instead, read with `FormsApi.get_revision` (published revisions only) and checked to belong to `template_id` → else 422 `REVISION_MISMATCH`.
    - (d) Insert the row (with `client_generated_id` through `aip.platform.db.idempotency.create_idempotent`, so a retried create returns the same inspection, 200 instead of 201).
    - (e) `ApprovalsApi.get_or_start_instance(conn, "inspection", inspection_id, project_id)`: `NoActiveDefinitionError` → 422 `NO_INSPECTION_WORKFLOW` and nothing written. Store `workflow_instance_id` and `state = instance.current_state` (`draft`).
    - (f) `emit(conn, "inspection.created", 1, ...)` with `{inspectionId, assetId, projectId, kind, templateRevisionId, source}`.
  - 5. `service.py` `transition(conn, policy, actor, inspection_id, action, comment, expected_sync_version)`: lock the inspection row, call `ApprovalsApi.transition(conn, policy, actor, instance_id, action, comment=..., expected_sync_version=...)`, and when the result is applied (not `pending_countersign`) set `state` to the new state and `emit(conn, "inspection.state_changed", 1, {inspectionId, assetId, projectId, from, to, action})` in the same transaction. Approvals' errors pass through unchanged (409 `INVALID_TRANSITION`, 403, 401 `STEP_UP_REQUIRED`, 422 `GUARD_FAILED`/`COMMENT_REQUIRED`, 202 for a pending countersign).
  - 6. `workflow.py`, imported by `__init__.py` so it registers at import time:
    - `register_record_resolver("inspection", resolve)` returning `RecordRef(project_id)` for a live inspection in the caller's tenant, else `None` (so `POST /api/v1/approvals/instances` binds an inspection only to its own project, ADR 0035 §6);
    - `register_guard_context_provider("inspection", facts)` returning read-only JSON facts `{kind, assetId, projectId, source}`; INSPECTIONS-02 and -03 add answer and step facts;
    - an outbox subscriber in `events.py`, `@subscriber("workflow.transitioned", 1)`, listed under `subscribes` in the manifest: for `recordType == "inspection"` it reads the instance with `ApprovalsApi.get_or_start_instance` and, only if `inspections.state` differs from `current_state`, sets it and emits `inspection.state_changed` v1. This covers transitions taken through `/api/v1/approvals/...` directly; a transition made through step 5 finds the state already equal and does nothing (idempotent on replay).
  - 7. Re-inspection (APPROVALS-05: `completed` is terminal, a re-inspection is a new inspection): `InspectionService.reinspect(conn, policy, actor, inspection_id)` needs `inspection.create`, refuses unless the source is `completed` (409 `NOT_COMPLETED`), and creates a new inspection with the same asset, project, template and kind, the template's **current** published revision, `source = 'reinspection'` and `source_ref_id` = the original.
  - 8. `routes.py` under `/api/v1/inspections`, every route `authenticated()` plus `require_active_tenant`, with the permission checked in the service against the inspection's project (the ADR 0035 §6 pattern, because project-scoped grants need the loaded record); another tenant's id → 404 before any permission check:
    - `POST /inspections {assetId, projectId?, templateId, templateRevisionId?, kind, clientGeneratedId?}` (`inspection.create`) → 201, source `manual` (`source`/`sourceRefId` are not accepted from clients in R1; SCOPEWORK-03 calls `create_inspection` directly);
    - `GET /inspections?assetId=&projectId=&state=&kind=&cursor=&limit=` (`inspection.view`, filtered to projects the caller may view);
    - `GET /inspections/{id}` (`inspection.view`) → the record plus `currentState`, `pendingCountersign` and `availableTransitions` (`action`, `labelKey`, `allowed`, `reasonKey`) from `ApprovalsApi.available_transitions`;
    - `POST /inspections/{id}/transition {action, comment?, expectedSyncVersion?}` (permission = the transition's `requiredPermission`, checked by approvals);
    - `GET /inspections/{id}/history` → `ApprovalsApi.get_history` (entries plus `chainValid`);
    - `POST /inspections/{id}/reinspect` → 201.

    Bodies are strict pydantic models (`extra="forbid"`), JSON is camelCase, validation errors are 422, explicit `operation_id`s.
  - 9. `api.py` publishes `InspectionsApi` with `create_inspection(conn, policy, actor, *, asset_id, project_id, template_id, kind, source, source_ref_id=None)` (the cross-module contract signature plus `source_ref_id`, which a scope task or re-inspection needs), `get_inspection(conn, inspection_id) -> InspectionOut | None` and `get_state(conn, inspection_id) -> str | None` (the instance's `current_state`). `events.py` declares the pydantic payloads; the manifest lists `[[events]]` `inspection.created` v1 and `inspection.state_changed` v1.
  - 10. Terms: add `inspection.source.<code>` and the error message keys (`inspection.error.template_not_published`, `.no_inspection_workflow`, `.not_completed`, `.revision_mismatch`) with en-AU text to `config/terms/en-AU/inspections.json`. Responses carry codes and keys, never display text.
- **acceptance**:
  - Creating an inspection writes one `inspections` row, one workflow instance in `draft` pinned to the active `inspection` definition version, and one `inspection.created` event, in one transaction; any failure writes none of them.
  - The pinned `template_revision_id` never changes; a newer published revision affects only new inspections and re-inspections.
  - Every lifecycle move goes through the approvals transition service (permission, guard, sign-off assurance, hash-chained history); `inspections.state` and `inspection.state_changed` follow every applied transition, whichever route took it, exactly once.
  - Another tenant's inspection is 404 on every route; RLS fails closed.
  - `InspectionsApi` exposes the contract functions; nothing outside `inspections` imports its other files (`tests/arch` boundary test stays green).
- **tests**:
  - **unit** (`test_unit.py`):
    - `InspectionCreate` with an unknown key `{"assetId": ..., "templateId": ..., "kind": "inspection", "state": "completed"}` → validation error on `state`.
    - `kind: "audit"` → validation error listing `inspection`, `itp`, `rfi`.
    - The facts provider's output for a fixture row → JSON-serialisable dict with exactly `kind`, `assetId`, `projectId`, `source` (uuids as strings).
    - Every `inspection.*` term key referenced in `schemas.py` and `service.py` exists in `config/terms/en-AU/inspections.json` → 0 missing.
  - **integration** (`test_inspections_db.py`, testcontainers-python Postgres, TESTING-01 tenants `kaefer-demo` and `tenant-b`; the conftest installs the APPROVALS-05 `inspection.standard` preset for `kaefer-demo` through the installer it exports from `aip.modules.approvals.api`, creates asset `TK-101` with `AssetsApi.create_asset` and publishes one coating template through the FORMS-01 forms interface; grants come from a test grant provider as in `projects/tests/conftest.py`: supervisor (`inspection.*`, `approvals.inspection.assign`, `approvals.inspection.approve`), inspector (`inspection.view`, `approvals.inspection.execute`), lead inspector (`approvals.inspection.review`), viewer (`inspection.view`)):
    - Supervisor `POST /api/v1/inspections {assetId: TK-101, projectId: KF-01, templateId, kind: "inspection"}` → 201 with `state: "draft"`, `templateRevisionId` = the published revision; `SELECT count(*) FROM inspections` = 1; 1 `domain_events` row with event name `inspection.created`; 1 `workflow_instances` row for record type `inspection`.
    - Same body plus the same `clientGeneratedId` twice → 201 then 200 with the same id; still 1 `inspections` row and 1 `domain_events` row for `inspection.created`.
    - Unknown `assetId` → 404 `ASSET_NOT_FOUND`; a template with only a draft revision → 422 `TEMPLATE_NOT_PUBLISHED`; tenant with no active `inspection` definition (`tenant-b`) → 422 `NO_INSPECTION_WORKFLOW`; each leaves `inspections` and `domain_events` counts unchanged.
    - Viewer `POST /api/v1/inspections` → 403 and 0 rows written.
    - Happy path through `POST /inspections/{id}/transition`: `ready`, `assign`, `start` (inspector), `submit` (inspector), `review_pass` (lead), `approve` (supervisor with an aal 2 session authenticated 1 minute ago) → each 200; final `state: "completed"`; 6 `domain_events` rows named `inspection.state_changed`, whose `from`/`to` pairs follow the preset; `GET /history` → 6 entries and `chainValid: true`.
    - `approve` by the supervisor with an aal 1 session whose user has MFA enrolled → 401 `STEP_UP_REQUIRED`; `state` stays `supervisor_review`; no new `domain_events` row.
    - Inspector `approve` at `supervisor_review` → 403; `approve` at `in_progress` → 409 `INVALID_TRANSITION`.
    - Publish a second template revision, then create another inspection → it pins revision 2; the first inspection still reports revision 1.
    - Bypass: take `ready` through `POST /api/v1/approvals/instances/{instanceId}/transition`, then run the outbox dispatcher once → `inspections.state` = `assignable` and exactly 1 `domain_events` row named `inspection.state_changed` for that move; dispatching the same event again → still 1.
    - `POST /api/v1/approvals/instances {recordType: "inspection", recordId, projectId: <another project>}` → 422 `PROJECT_MISMATCH` (the resolver's project wins).
    - `POST /inspections/{completed id}/reinspect` → 201 with `source: "reinspection"`, `sourceRefId` = the original, `state: "draft"`; on a `draft` inspection → 409 `NOT_COMPLETED`.
    - A `tenant-b` user `GET /api/v1/inspections/{kaefer id}` → 404, `GET /api/v1/inspections` → 0 items, transition → 404.
    - As `aip_app` with no `app.tenant_id`: `SELECT count(*) FROM inspections` → 0; `INSERT INTO inspections` → SQLSTATE 42501.
    - Make `emit` raise after the insert → 500; `inspections` and `workflow_instances` counts unchanged.
  - **e2e**:
    - API-only task: covered by the in-process HTTP integration tests above, as ADR 0035 §9 decided for approvals (the deployed stack has no seeded asset or published template yet). INSPECTIONS-04 adds the Playwright journey, cross-tenant 404 and axe check for the inspection pages.
