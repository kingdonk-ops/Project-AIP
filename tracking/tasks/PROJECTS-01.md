# PROJECTS-01 — Projects + sites tables and CRUD API

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

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
3. ADRs: 0002 (Kysely, SQL migrations, `withTenant`, roles), 0004 (layout), 0007 (M0 scope)
4. Only if the step needs it: the `sites` and `projects` tables in [`data-model.md`](../../docs/blueprint/modules/projects/data-model.md)

## Spec

Create the first real tenant-scoped register: `projects` and `sites` with RLS, and a permission-checked CRUD API that PROJECTS-02 and TESTING-09 build on.

- **files**:
  - db/migrations/<timestamp>_projects_sites.sql (timestamp assigned at PR time, never a number)
  - apps/api/src/modules/projects/module.ts
  - apps/api/src/modules/projects/api.ts
  - apps/api/src/modules/projects/service.ts
  - apps/api/src/modules/projects/repository.ts
  - apps/api/src/modules/projects/projects.controller.ts
  - apps/api/src/modules/projects/sites.controller.ts
  - apps/api/src/modules/projects/schemas.ts
  - apps/api/src/modules/projects/events.ts
  - apps/api/src/modules/projects/permissions.ts
  - apps/api/src/modules/projects/manifest.json
  - apps/api/src/modules/projects/tests/
- **steps**:
  - 1. Scaffold the module with `tools/new-module.ts projects`. Do not hand-create the folder.
  - 2. Write one migration from the `db/templates/` tenant-table template. `sites`: id, tenant_id, code, name, lat numeric(9,6), lng numeric(9,6) (CHECK lat between -90 and 90 and lng between -180 and 180), timezone, is_system, created_at, updated_at, deleted_at. `projects`: id, tenant_id, code, name, client_company_id (uuid, nullable, no FK until contacts exists), site_id (FK sites, nullable), classification_id and template_id (uuid, nullable, no FK yet), region, timezone, currency char(3), status, closed_at, sync_version int default 1, created_at, updated_at, deleted_at. Both tables get FORCE RLS with the ADR 0002 `NULLIF(current_setting('app.tenant_id', true), '')::uuid` policy using both USING and WITH CHECK. Grant aip_app SELECT, INSERT and UPDATE, but not DELETE (deletes are soft).
  - 3. Add the indexes: unique (tenant_id, upper(code)) WHERE deleted_at IS NULL on both tables, plus (tenant_id, status) and (tenant_id, site_id) on projects. Store a plain lat/lng pair instead of a PostGIS geography column: ADR 0002 says add PostGIS only when a module needs spatial queries.
  - 4. In schemas.ts, define Zod schemas with nestjs-zod. Project code must match `^[A-Z0-9][A-Z0-9-]{1,31}$` and is upper-cased on input (`l592` is stored as `L592`). Status is one of `draft|active|closing|archived`. Currency is ISO 4217 from a fixed list. Timezone must be a valid IANA zone (`Intl.supportedValuesOf('timeZone')`). Region is a key from TENANCY-01's `deployment_regions`.
  - 5. In repository.ts, implement Kysely queries that run only inside `withTenant(ctx, fn)` from `apps/api/src/platform/db`. Never import `pg` or Kysely anywhere else. Default reads filter `deleted_at IS NULL`.
  - 6. In service.ts, implement list (cursor pagination: `limit` 1–200 with default 50, opaque `cursor` encoding (code, id), `sort=code|name|updated_at`, filters `status`, `siteId` and `q` on code/name ILIKE), get, create (status defaults to draft) and update. Update needs `syncVersion` in the body and runs `UPDATE ... WHERE sync_version = $n`; a mismatch raises 409 with the current row. Status may only move forward: draft→active→closing→archived, plus closing→active. Archive sets closed_at. The closeout gate is out of scope here. Sites get list, create, update and soft delete. A site referenced by a live project cannot be deleted (409 SITE_IN_USE).
  - 7. Add the controllers under `/api/v1/projects` and `/api/v1/sites`: GET list, GET `/:id`, POST, PATCH `/:id`, and DELETE `/:id` for sites only. Protect every route with the permission guard that ACCESS-01 exports. Permissions are `project.view`, `project.create`, `project.update`, `project.archive`, `site.view` and `site.manage`; declare them in permissions.ts and manifest.json. An archive (PATCH status=archived) also needs `project.archive`. If the user lacks a role yet, use the bootstrap that ACCESS-01 provides until ACCESS-02 seeds real roles.
  - 8. Map errors to HTTP codes. A duplicate code returns 409 `PROJECT_CODE_TAKEN` / `SITE_CODE_TAKEN`. A row in another tenant or a soft-deleted row returns 404 (RLS hides it, so never 403). A Zod failure returns 422 with field paths.
  - 9. Emit `project.created`, `project.updated` and `project.archived` in the same transaction through the outbox `emit()` from ARCH-05, with payload `{projectId, code, status, before?, after?}`. Declare the event schemas in events.ts.
  - 10. Export only `ProjectsApi` from api.ts (`getProject`, `assertProjectExists`, `listProjectIds`). Regenerate the Kysely types (kysely-codegen), the OpenAPI document and `packages/api-client`, and commit them with no drift.
- **acceptance**:
  - The migration applies on an empty database and re-runs as a no-op through the runner. TESTING-02's schema guard passes for both tables.
  - A project code is unique per tenant, ignoring case. The same code can exist in two tenants.
  - A user in tenant B gets 404, not 403, for tenant A's project id. List endpoints never return another tenant's rows.
  - Every route is denied without the matching permission (deny by default). No route lacks a permission decorator.
  - `packages/api-client` exposes typed hooks for list/get/create/update projects and sites, and the drift check is green.
- **tests**:
  - **unit**:
    - `ProjectCreate.parse({code:'l592', name:'Ichthys KIPS', currency:'AUD', timezone:'Australia/Perth'})` returns code `'L592'` and status `'draft'`.
    - Code `'ab cd'` fails with a Zod issue at path `['code']`. Currency `'XXX'` fails at `['currency']`. Timezone `'Mars/Olympus'` fails at `['timezone']`.
    - `canTransition('draft','active')` is true. `canTransition('archived','active')` and `canTransition('draft','archived')` are false.
    - The cursor codec round-trips `{code:'L592', id:'0190…'}` and rejects a tampered base64 string with `InvalidCursorError`.
  - **integration** (Testcontainers Postgres, connected as aip_app):
    - As tenant A, POST `{code:'L592', name:'Ichthys'}`. Expected: 201. POST `{code:'l592'}` again. Expected: 409 `PROJECT_CODE_TAKEN`. As tenant B, POST `{code:'L592'}`. Expected: 201.
    - As tenant B, GET `/api/v1/projects/<A's id>`. Expected: 404. As tenant B, GET `/api/v1/projects`. Expected: A's project is absent.
    - As aip_app with no `app.tenant_id` set, run `SELECT count(*) FROM projects`. Expected: 0. An INSERT with no tenant set fails the WITH CHECK.
    - Create 120 projects and page with limit=50. Expected: pages of 50, 50 and 20, no duplicates, and `nextCursor` is null on the last page.
    - PATCH with a stale `syncVersion` (1 when the stored value is 2). Expected: 409 with the body's `current.syncVersion` equal to 2.
    - A user without `project.create` POSTs. Expected: 403, and no row or outbox event is written.
    - Create a project, then roll back the surrounding transaction in the service test. Expected: no `project.created` row in `domain_events`.
    - DELETE a site used by an active project. Expected: 409 `SITE_IN_USE`.
  - **e2e**:
    - With the compose stack running, a seeded kaefer-demo admin calls POST then GET `/api/v1/projects` through the generated client. Expected: the new project is listed with status `draft`. TESTING-09 covers the UI journey.
