# PROJECTS-01 — Projects + sites tables and CRUD API
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`projects`](../../docs/blueprint/modules/projects/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, DATABASE-02, TENANCY-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/projects/README.md`](../../docs/blueprint/modules/projects/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0002](../../docs/adr/0002-data-access-and-migrations.md) (SQLAlchemy Core, Alembic raw SQL, `with_tenant`, roles), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox), [0004](../../docs/adr/0004-repository-layout.md) (layout, OpenAPI → `packages/api-client`), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (M0 scope)
4. Only if the step needs it: the `sites` and `projects` tables in [`data-model.md`](../../docs/blueprint/modules/projects/data-model.md)

## Spec

Create the first real tenant-scoped register: `projects` and `sites` with RLS, and a permission-checked FastAPI CRUD API that PROJECTS-02 and TESTING-09 build on.

- **files**:
  - apps/api/migrations/versions/<rev>_projects_sites.py (Alembic revision id assigned at PR time)
  - apps/api/aip/modules/projects/__init__.py (exports `api` only)
  - apps/api/aip/modules/projects/api.py
  - apps/api/aip/modules/projects/tables.py
  - apps/api/aip/modules/projects/schemas.py
  - apps/api/aip/modules/projects/repository.py
  - apps/api/aip/modules/projects/service.py
  - apps/api/aip/modules/projects/policies.py
  - apps/api/aip/modules/projects/events.py
  - apps/api/aip/modules/projects/routes.py
  - apps/api/aip/modules/projects/manifest.toml
  - apps/api/aip/modules/projects/tests/
  - packages/api-client/ (regenerated, never hand-edited)
- **steps**:
  - 1. Scaffold the module with `python tools/new_module.py projects`. Do not hand-create the folder.
  - 2. Write one Alembic revision (raw SQL via `op.execute`) from the `db/templates/` tenant-table template. `sites`: id, tenant_id, code, name, lat numeric(9,6), lng numeric(9,6) (CHECK lat between -90 and 90 and lng between -180 and 180), timezone, is_system, created_at, updated_at, deleted_at. `projects`: id, tenant_id, code, name, client_company_id (uuid, nullable, no FK until contacts exists), site_id (FK sites, nullable), classification_id and template_id (uuid, nullable, no FK yet), region, timezone, currency char(3), status, closed_at, sync_version int default 1, created_at, updated_at, deleted_at. Both tables get FORCE RLS with the ADR 0002 `NULLIF(current_setting('app.tenant_id', true), '')::uuid` policy using both USING and WITH CHECK. Grant aip_app SELECT, INSERT and UPDATE, but not DELETE (deletes are soft). IDs are UUIDv7 generated in the app.
  - 3. Add the indexes: unique (tenant_id, upper(code)) WHERE deleted_at IS NULL on both tables, plus (tenant_id, status) and (tenant_id, site_id) on projects. Store a plain lat/lng pair instead of a PostGIS geography column: ADR 0002 says add PostGIS only when a module needs spatial queries. Declare both tables as SQLAlchemy Core `Table` objects in `tables.py` (the CI schema-diff check compares them).
  - 4. In schemas.py, define Pydantic v2 models (`ProjectCreate`, `ProjectUpdate`, `ProjectOut`, `ProjectPage`, `SiteCreate`, `SiteUpdate`, `SiteOut`, `SitePage`) with camelCase aliases. Project code must match `^[A-Z0-9][A-Z0-9-]{1,31}$` after a `mode='before'` validator upper-cases it (`l592` is stored as `L592`). Status is `Literal['draft','active','closing','archived']`. Currency is ISO 4217 from a fixed list. Timezone must be in `zoneinfo.available_timezones()`. Region is a key from TENANCY-01's `deployment_regions` (checked in the service, since it needs the database).
  - 5. In repository.py, implement SQLAlchemy Core queries that take the tenant-bound `AsyncConnection` from `async with with_tenant(ctx) as conn:` (`aip.platform.db`). Never create engines or connections anywhere else (import-linter enforces it). Default reads filter `deleted_at IS NULL`.
  - 6. In service.py, implement list (cursor pagination: `limit` 1–200 with default 50, opaque `cursor` encoding (code, id) as base64url JSON with an HMAC, `sort=code|name|updated_at`, filters `status`, `siteId` and `q` on code/name ILIKE), get, create (status defaults to draft) and update. Update needs `syncVersion` in the body and runs `UPDATE ... WHERE sync_version = :n`; a mismatch raises 409 with the current row. Status may only move forward: draft→active→closing→archived, plus closing→active (`can_transition` in `policies.py`). Archive sets closed_at. The closeout gate is out of scope here. Sites get list, create, update and soft delete. A site referenced by a live project cannot be deleted (409 SITE_IN_USE).
  - 7. Add the FastAPI `APIRouter`s in routes.py under `/api/v1/projects` and `/api/v1/sites`: GET list, GET `/{id}`, POST, PATCH `/{id}`, and DELETE `/{id}` for sites only, each with explicit `response_model`s and `operation_id`s so the generated client has stable hook names. Protect every route with ACCESS-01's `requires(...)` dependency. Permissions are `project.view`, `project.create`, `project.update`, `project.archive`, `site.view` and `site.manage`; declare them in `manifest.toml`. An archive (PATCH status=archived) also calls `assert_can(principal, 'project.archive', resource)`. If the user lacks a role yet, use the bootstrap that ACCESS-01 provides until ACCESS-02 seeds real roles.
  - 8. Map errors to HTTP codes with exception handlers. A duplicate code (unique violation from asyncpg) returns 409 `PROJECT_CODE_TAKEN` / `SITE_CODE_TAKEN`. A row in another tenant or a soft-deleted row returns 404 (RLS hides it, so never 403). A Pydantic validation failure returns 422 with field paths (`loc`).
  - 9. Emit `project.created`, `project.updated` and `project.archived` in the same transaction through the outbox `emit(conn, ...)` from ARCH-05 (`aip.platform.events`), with payload `{projectId, code, status, before?, after?}`. Declare the event payload models in events.py.
  - 10. Export only `ProjectsApi` from api.py (`get_project`, `assert_project_exists`, `list_project_ids`). Regenerate the OpenAPI document and `packages/api-client` (openapi-typescript + orval), and commit them with no drift.
- **acceptance**:
  - `alembic upgrade head` applies on an empty database and a second run is a no-op. TESTING-02's schema guard passes for both tables.
  - A project code is unique per tenant, ignoring case. The same code can exist in two tenants.
  - A user in tenant B gets 404, not 403, for tenant A's project id. List endpoints never return another tenant's rows.
  - Every route is denied without the matching permission (deny by default). No route lacks an access declaration.
  - `packages/api-client` exposes typed hooks for list/get/create/update projects and sites, and the drift check is green.
- **tests** (pytest; integration uses testcontainers-python Postgres connected as aip_app, and `httpx.AsyncClient`):
  - **unit**:
    - `ProjectCreate.model_validate({'code':'l592', 'name':'Ichthys KIPS', 'currency':'AUD', 'timezone':'Australia/Perth'})` returns code `'L592'` and status `'draft'`.
    - Code `'ab cd'` raises `ValidationError` with `loc == ('code',)`. Currency `'XXX'` fails at `('currency',)`. Timezone `'Mars/Olympus'` fails at `('timezone',)`.
    - `can_transition('draft','active')` is true. `can_transition('archived','active')` and `can_transition('draft','archived')` are false.
    - The cursor codec round-trips `{code:'L592', id:'0190…'}` and rejects a tampered base64 string with `InvalidCursorError`.
  - **integration**:
    - As tenant A, POST `{code:'L592', name:'Ichthys'}`. Expected: 201. POST `{code:'l592'}` again. Expected: 409 `PROJECT_CODE_TAKEN`. As tenant B, POST `{code:'L592'}`. Expected: 201.
    - As tenant B, GET `/api/v1/projects/<A's id>`. Expected: 404. As tenant B, GET `/api/v1/projects`. Expected: A's project is absent.
    - As aip_app with no `app.tenant_id` set, run `SELECT count(*) FROM projects`. Expected: 0. An INSERT with no tenant set fails the WITH CHECK.
    - Create 120 projects and page with limit=50. Expected: pages of 50, 50 and 20, no duplicates, and `nextCursor` is null on the last page.
    - PATCH with a stale `syncVersion` (1 when the stored value is 2). Expected: 409 with the body's `current.syncVersion` equal to 2.
    - A user without `project.create` POSTs. Expected: 403, and no row or outbox event is written.
    - Create a project, then roll back the surrounding transaction in the service test. Expected: no `project.created` row in `domain_events`.
    - DELETE a site used by an active project. Expected: 409 `SITE_IN_USE`.
  - **e2e**:
    - With the compose stack running, a seeded kaefer-demo admin calls POST then GET `/api/v1/projects` through the generated client (a small Vitest/Node script in `e2e/`). Expected: the new project is listed with status `draft`. TESTING-09 covers the UI journey.
