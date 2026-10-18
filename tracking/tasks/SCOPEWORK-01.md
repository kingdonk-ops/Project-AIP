# SCOPEWORK-01 — RSW records, disciplines and ordered scope tasks with requirement flags

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`scope_work`](../../docs/blueprint/modules/scope_work/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/scope_work/README.md`](../../docs/blueprint/modules/scope_work/README.md) and, for columns only, [`data-model.md`](../../docs/blueprint/modules/scope_work/data-model.md) (`rsws`, `rsw_disciplines`, `scope_tasks`, `scope_vocabularies`)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (SQLAlchemy Core, Alembic raw SQL, `with_tenant`), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction), [0004](../../docs/adr/0004-repository-layout.md) (only `api.py` crosses modules), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0025](../../docs/adr/0025-time-and-timezones.md) (dates and UTC), [0027](../../docs/adr/0027-default-role-permission-expansion.md) (permission verbs), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 decisions)
4. The module pattern to copy: `apps/api/aip/modules/projects/` (`tables.py`, `schemas.py`, `repository.py`, `service.py`, `routes.py`, `manifest.toml`, `tests/conftest.py`) and the migration `apps/api/migrations/versions/202610131300_projects_sites.py`
5. Access methods are answered in [`01-decisions.md`](../../docs/blueprint/01-decisions.md) (MEWP and Ladder split, tenant-editable list; ADR 0036). This task does **not** seed them: SCOPEWORK-06 does.

> Out of scope: the completion gate and stored evaluations (SCOPEWORK-02), creating the linked inspection or ITP
> and the hold-point link (SCOPEWORK-03), register and detail pages (SCOPEWORK-04), vocabulary seed data
> (SCOPEWORK-06), hours and delays (`rsw_hours`, `rsw_delay_records`: SCOPEWORK-07), RSW numbering
> schemes, computed deadlines, RSW templates, RFI and cost-item links.

## Spec

Create the `scope_work` module with RSW records, their disciplines and ordered scope tasks carrying requirement flags, plus the tenant-editable scope vocabularies the RSW's key fields are checked against (tag: extend).

- **files**:
  - apps/api/aip/modules/scope_work/__init__.py
  - apps/api/aip/modules/scope_work/manifest.toml
  - apps/api/aip/modules/scope_work/tables.py
  - apps/api/aip/modules/scope_work/schemas.py
  - apps/api/aip/modules/scope_work/repository.py
  - apps/api/aip/modules/scope_work/service.py
  - apps/api/aip/modules/scope_work/policies.py
  - apps/api/aip/modules/scope_work/vocabularies.py
  - apps/api/aip/modules/scope_work/events.py
  - apps/api/aip/modules/scope_work/routes.py
  - apps/api/aip/modules/scope_work/api.py
  - apps/api/aip/modules/scope_work/tests/__init__.py
  - apps/api/aip/modules/scope_work/tests/conftest.py
  - apps/api/aip/modules/scope_work/tests/test_unit.py
  - apps/api/aip/modules/scope_work/tests/test_scope_work_db.py
  - apps/api/migrations/versions/<timestamp>_scope_work_rsws_tasks.py
  - config/terms/en-AU/scope_work.json
- **steps**:
  - 1. Scaffold with `python3 tools/new_module.py scope_work`. Manifest: `id = "scope_work"`, `context = "scope_work"`, `depends_on = ["tenancy", "projects", "assets"]`, `permission_namespaces = ["rsw", "scope"]`. Permissions (verbs from ADR 0027, so the default roles pick them up at the right level): `rsw.view`, `rsw.create`, `rsw.update`, `rsw.delete`, `scope.vocab.manage` (admin only). Events: `rsw.created` v1, `rsw.updated` v1. `term_keys` lists the RSW label keys from step 9.
  - 2. Migration `<timestamp>_scope_work_rsws_tasks.py` (forward-only, `downgrade` raises), each table rendered with `render_template("tenant_table", ...)` from `aip.platform.db.templates` (uuid PK, `tenant_id`, timestamps, `deleted_at`, FORCE RLS with the fail-closed `NULLIF` policy, the template's grants), then `REVOKE DELETE ... FROM aip_app` on each (deletes are soft):
    - (a) create `scope_vocabularies` with `vocab text NOT NULL`, `key text NOT NULL`, `label text NOT NULL`, `sort_order integer NOT NULL DEFAULT 0`, `config jsonb NOT NULL DEFAULT '{}'`, `is_active boolean NOT NULL DEFAULT true`. Checks: `vocab IN ('discipline','priority','access_method','inspection_technique','delay_reason')`, `key ~ '^[a-z][a-z0-9_]{0,62}$'`, `label <> ''`. Unique `(tenant_id, vocab, key)` (all rows: a key is never reused, it is deactivated). No seed rows: the default vocabularies are SCOPEWORK-06.
    - (b) create `rsws` with `sync=True` (adds `client_generated_id` and `sync_version`) and the data-model columns: `project_id uuid NOT NULL`, `asset_id uuid NOT NULL`, `rsw_number text NOT NULL`, `revision integer NOT NULL DEFAULT 0`, `location`, `corrosion_environment`, `observation`, `remedial_works`, `notification_no` (text NULL), `mandated_completion_date date NULL`, `priority text NULL`, `work_order`, `order_no`, `ctr`, `wbs`, `tier` (text NULL), `estimated_hours numeric(10,1) NULL`, `metres_to_scan numeric(10,2) NULL`, `access_method text NULL`, `inspection_technique text NULL`, `procedure_refs jsonb NOT NULL DEFAULT '[]'`, `status text NOT NULL DEFAULT 'draft'`, `progress_pct numeric(5,2) NOT NULL DEFAULT 0`, `completed_at timestamptz NULL`. Checks: `rsw_number <> ''`, `revision >= 0`, `status IN ('draft','in_progress','completed','cancelled')`, `progress_pct BETWEEN 0 AND 100`, `estimated_hours >= 0`, `metres_to_scan >= 0`, `(status = 'completed') = (completed_at IS NOT NULL)`, `jsonb_typeof(procedure_refs) = 'array'`. `UNIQUE (id, tenant_id)` for child FKs. Indexes: unique `(tenant_id, project_id, upper(rsw_number), revision) WHERE deleted_at IS NULL`, `(tenant_id, asset_id)`, `(tenant_id, project_id, status, priority)`, `(tenant_id, wbs)`. `computed_deadline` is left out (deferred in the README).
    - (c) create `rsw_disciplines` with `rsw_id uuid NOT NULL`, `discipline_key text NOT NULL`, `sequence integer NOT NULL`. FK `(rsw_id, tenant_id) REFERENCES rsws (id, tenant_id)`. `UNIQUE (id, tenant_id)`. Unique `(rsw_id, discipline_key) WHERE deleted_at IS NULL` and unique `(rsw_id, sequence) WHERE deleted_at IS NULL`. There is no `disciplines` table in this codebase: a discipline is a `scope_vocabularies` row with `vocab = 'discipline'`, so `discipline_key` replaces the data model's `discipline_id`.
    - (d) create `scope_tasks` with `sync=True` and `rsw_id uuid NOT NULL`, `rsw_discipline_id uuid NOT NULL`, `component_asset_id uuid NULL`, `name text NOT NULL`, `sequence integer NOT NULL`, `requires_itp`, `requires_inspection`, `requires_rfi`, `requires_consumables` (boolean NOT NULL DEFAULT false), `inspection_template_id uuid NULL`, `itp_template_id uuid NULL`, `itp_id uuid NULL`, `inspection_id uuid NULL`, `hold_point_id uuid NULL`, `status text NOT NULL DEFAULT 'open'`. Checks: `name <> ''`, `sequence >= 1`, `status IN ('open','done','cancelled')`. FKs `(rsw_id, tenant_id) → rsws` and `(rsw_discipline_id, tenant_id) → rsw_disciplines`. Indexes: unique `(rsw_discipline_id, sequence) WHERE deleted_at IS NULL`, `(tenant_id, rsw_id)`, `(tenant_id, component_asset_id)`, unique `(tenant_id, hold_point_id) WHERE hold_point_id IS NOT NULL AND deleted_at IS NULL` (one hold-point link per task, used by SCOPEWORK-03), `(tenant_id, requires_itp) WHERE itp_id IS NULL AND requires_itp`. `itp_id`, `inspection_id` and `hold_point_id` are written only by SCOPEWORK-03; `rfi_id` and `cost_item_id` are left out (no RFI or cost module in R1).
    - (e) No foreign keys to other modules' tables (`projects`, `assets`, inspections): those ids are checked through the owning module's `api.py` in the service (ADR 0004).
  - 3. `tables.py`: SQLAlchemy Core `Table`s for the four tables on the shared `MetaData` (as `projects/tables.py`). `repository.py`: plain Core queries on the caller's connection, every read filtered on `deleted_at IS NULL`, with `SELECT ... FOR UPDATE` helpers for an RSW and a task.
  - 4. `vocabularies.py`: `VOCABS = ("discipline", "priority", "access_method", "inspection_technique", "delay_reason")` and `assert_active_key(conn, vocab, key)`, which raises a 422 `UNKNOWN_VOCAB_KEY` with `{field, vocab, key}` unless an active row exists in the caller's tenant. `None` is always allowed for the nullable RSW fields. Routes (`/api/v1/scope-vocabularies`):
    - `GET ?vocab=access_method` (`rsw.view`) → active rows ordered by `sort_order, key`; `?includeInactive=true` needs `scope.vocab.manage`.
    - `POST {vocab, key, label, sortOrder?, config?}` (`scope.vocab.manage`) → 201; a duplicate `(vocab, key)` → 409 `VOCAB_KEY_EXISTS`.
    - `PATCH /{id} {label?, sortOrder?, isActive?, config?}` (`scope.vocab.manage`) → 200. `key` and `vocab` are immutable (unknown or forbidden keys → 422). There is no delete: a key is deactivated, so existing RSWs keep a valid reference.
  - 5. `schemas.py`: Pydantic v2 models with `ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")` as in projects: `RswCreate`, `RswUpdate` (all optional plus required `expectedSyncVersion`), `RswOut` (includes `disciplines[]`, each with `tasks[]` ordered by `sequence`), `DisciplineCreate {disciplineKey}`, `TaskCreate`, `TaskUpdate`, `TaskOut`, `OrderBody {ids: list[UUID]}`. `status`, `progressPct`, `completedAt`, `itpId`, `inspectionId` and `holdPointId` are output only. `procedureRefs` is a list of `{kind: 'document'|'standard', ref: str}` (max 50). Hours are multiples of 0.1, `metresToScan` of 0.01, both `>= 0`.
  - 6. `service.py` (`RswService`, `ScopeTaskService`), every write inside the request's `with_tenant` transaction (`aip.platform.db.with_tenant`):
    - (a) Create RSW: `ProjectsApi().assert_project_exists(conn, project_id)` and `aip.modules.assets.api.AssetsApi().assert_asset_exists(conn, asset_id)` (another tenant's id → 404), `assert_active_key` for `priority`, `access_method` and `inspection_technique`, insert with a UUIDv7 id through `aip.platform.db.idempotency.create_idempotent` when `clientGeneratedId` is sent, then `emit(conn, "rsw.created", 1, Aggregate("rsw", id), {rswId, projectId, assetId, rswNumber, revision}, asset_id=asset_id)` (`aip.platform.events.outbox.emit`). A duplicate live `(project, rsw_number, revision)` → 409 `RSW_NUMBER_EXISTS`.
    - (b) Update RSW: `aip.platform.db.concurrency.update_with_version` with `expectedSyncVersion` (stale → 409 `SYNC_VERSION_CONFLICT` with the current row); vocabulary fields re-checked; `project_id` and `asset_id` cannot change. Emit `rsw.updated` v1 `{rswId, changed: [field names]}`. A `completed` or `cancelled` RSW → 409 `RSW_CLOSED`.
    - (c) Status (`policies.py`, as `projects/policies.py`): `ALLOWED_TRANSITIONS = {"draft": {"in_progress", "cancelled"}, "in_progress": {"cancelled"}, "completed": set(), "cancelled": set()}`. `POST /rsws/{id}/start` and `POST /rsws/{id}/cancel` (`rsw.update`) move status and emit `rsw.updated`. `completed` is reachable only through the SCOPEWORK-02 gate; nothing in this task can set it.
    - (d) Soft delete RSW (`rsw.delete`): only in `draft`, else 409 `RSW_NOT_DRAFT`; its disciplines and tasks are soft-deleted in the same transaction.
    - (e) Disciplines: `POST /rsws/{id}/disciplines {disciplineKey}` checks the key against `discipline` and appends at `max(sequence)+1`; the same live key twice → 409 `DISCIPLINE_EXISTS`. `DELETE /rsws/{id}/disciplines/{rdId}` → 409 `DISCIPLINE_HAS_TASKS` while live tasks remain. `PUT /rsws/{id}/discipline-order {ids}` must list exactly the live disciplines (else 422 `ORDER_MISMATCH`) and renumbers them 1..n.
    - (f) Tasks: `POST /rsws/{id}/disciplines/{rdId}/tasks` appends at `max(sequence)+1` within the discipline. A `componentAssetId` must be in `AssetsApi().subtree_ids(conn, rsw.asset_id)`, else 422 `COMPONENT_NOT_IN_ASSET`. `PATCH /scope-tasks/{id}` with `expectedSyncVersion` changes name, flags, template ids, component and status (`open`/`done`/`cancelled`). `DELETE /scope-tasks/{id}` is a soft delete. `PUT /rsws/{id}/disciplines/{rdId}/task-order {ids}` renumbers in two passes (negative sequences first, then 1..n) so the partial unique index never trips. Any task write on a `completed` or `cancelled` RSW → 409 `RSW_CLOSED`.
    - (g) Reads: `GET /rsws?projectId=&status=&limit=&cursor=` (`rsw.view`; keyset on `id`, limit ≤ 200; the full register is SCOPEWORK-04) and `GET /rsws/{id}` (nested disciplines and tasks).
  - 7. `routes.py`: one `APIRouter` mounted under `/api/v1`, every route declaring `requires(...)` from `aip.platform.access` (deny by default) with a `Resource(project_id=...)` from the RSW (as `_project_resource` in `projects/routes.py`), `require_active_tenant` from `aip.modules.tenancy.api`, and explicit `operation_id`s (`scope_work_rsw_create`, ...). Errors use the projects `ErrorBody` shape `{code, messageKey, detail}`.
  - 8. `api.py` (`ScopeWorkApi`): `get_rsw(conn, rsw_id) -> RswOut | None`, `assert_rsw_exists(conn, rsw_id)`, `list_tasks(conn, rsw_id) -> list[TaskOut]` for later rows and other modules. Register the module's tables with the schema guard as the template does.
  - 9. Terms in `config/terms/en-AU/scope_work.json` (keep the existing `access.method.*` entries and the file's `{text, description}` format): `scope_work.rsw.label` "RSW" and `scope_work.rsw.label_plural` "RSWs" (the renamable RSW label: code and responses never contain the word, only this key), `scope_work.rsw.status.<draft|in_progress|completed|cancelled>`, `scope_work.task.status.<open|done|cancelled>`, `scope_work.requirement.<itp|inspection|rfi|consumables>`, and one `scope_work.error.<code>` per error code above.
- **acceptance**:
  - The four tables exist with FORCE RLS, the fail-closed policy and no `DELETE` grant for `aip_app`; the schema guard passes.
  - No `scope_vocabularies` rows are created by the migration or at tenant provisioning.
  - Every create and status change writes exactly one `domain_events` row in the same transaction; a failure after the insert leaves neither.
  - An RSW's `access_method`, `inspection_technique` and `priority` and a discipline's key are always an active vocabulary key of the same tenant, or null.
  - No route can set `status = 'completed'`, `completed_at`, `progress_pct`, `itp_id`, `inspection_id` or `hold_point_id`.
  - The OpenAPI client regenerates without drift.
- **tests**:
  - **unit**:
    - `can_transition("draft", "in_progress")` → `True`; `("in_progress", "completed")` → `False`; `("completed", "draft")` → `False`; `("cancelled", "in_progress")` → `False`.
    - `RswCreate.model_validate({..., "status": "completed"})` → validation error on `status` (extra forbidden). `estimatedHours: 1.25` → error; `12.5` → ok. `procedureRefs: [{"kind":"url","ref":"x"}]` → error on `kind`.
    - Two-pass renumbering helper: current `[a:1, b:2, c:3]`, new order `[c, a, b]` → updates `[(c,-1),(a,-2),(b,-3),(c,1),(a,2),(b,3)]`.
    - `TaskCreate` with `holdPointId` → error (extra forbidden).
  - **integration** (pytest, testcontainers-python Postgres, TESTING-01 tenants `kaefer-demo` and `tenant-b`, test grant provider as in `projects/tests/conftest.py`; projects seeded as superuser, assets made with `AssetsApi.create_asset`):
    - As `aip_app` with `app.tenant_id` unset: `SELECT count(*) FROM rsws` → 0 rows; an insert → SQLSTATE 42501.
    - After `alembic upgrade head`: `SELECT count(*) FROM scope_vocabularies` (as superuser) → 0.
    - `POST /api/v1/scope-vocabularies {vocab:'access_method', key:'rope_access', label:'Rope access'}` as a tenant admin → 201; the same again → 409 `VOCAB_KEY_EXISTS`; as a user with only `rsw.view` → 403.
    - `POST /api/v1/rsws {projectId: P1, assetId: A1, rswNumber:'RSW-0001', priority:'p1', accessMethod:'rope_access'}` with `p1` and `rope_access` active → 201, `status:'draft'`, `syncVersion:1`, `progressPct:0`; `SELECT event_name FROM domain_events` has 1 `rsw.created` row with `aggregate_id` = the RSW id.
    - The same body with `accessMethod:'helicopter'` → 422 `UNKNOWN_VOCAB_KEY` `{field:'accessMethod', vocab:'access_method', key:'helicopter'}`; after `PATCH /scope-vocabularies/{id} {isActive:false}` on `rope_access`, a new RSW with `rope_access` → 422, while the existing RSW still reads `accessMethod:'rope_access'`.
    - A second RSW `RSW-0001` rev 0 in P1 → 409 `RSW_NUMBER_EXISTS`; `rsw-0001` rev 1 → 201.
    - `assetId` of a `tenant-b` asset → 404; `projectId` of a `tenant-b` project → 404; `GET /api/v1/rsws/{kaefer rsw id}` as a `tenant-b` user → 404.
    - Add disciplines `coating` then `welding` → sequences 1, 2; `coating` again → 409 `DISCIPLINE_EXISTS`; `disciplineKey:'plumbing'` (not in vocab) → 422 `UNKNOWN_VOCAB_KEY`.
    - Add tasks `test`, `blast`, `coat` under `coating` → sequences 1, 2, 3; `PUT task-order [coat, test, blast]` → `GET` shows that order with sequences 1, 2, 3; an order listing two of three → 422 `ORDER_MISMATCH`.
    - A task with `componentAssetId` of an asset outside the RSW asset's subtree → 422 `COMPONENT_NOT_IN_ASSET`; a child of the RSW asset → 201.
    - `PATCH /api/v1/rsws/{id}` with `expectedSyncVersion: 1` → 200 `syncVersion:2`; again with `1` → 409 `SYNC_VERSION_CONFLICT`.
    - `POST /rsws/{id}/start` → `in_progress`; `DELETE /rsws/{id}` → 409 `RSW_NOT_DRAFT`; `POST /cancel` → `cancelled`; then `POST .../tasks` → 409 `RSW_CLOSED`.
    - `PATCH /api/v1/rsws/{id} {"status":"completed","expectedSyncVersion":1}` → 422 (extra forbidden); `PATCH /scope-tasks/{id} {"inspectionId": "...", ...}` → 422.
    - Make `emit` raise in a test hook during create → 500; `SELECT count(*) FROM rsws` for that number → 0.
    - As `aip_app`: `DELETE FROM rsws` → `permission denied`.
  - **e2e**:
    - Covered by the integration tests above, which drive the real app over HTTP on real Postgres: this row has no page, and the repo has no Playwright API project yet. The Playwright journey, cross-tenant check and axe check ship with the RSW pages in SCOPEWORK-04.
