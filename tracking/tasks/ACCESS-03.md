# ACCESS-03 — Scope tables and RLS project predicates; policy/RLS parity tests

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-02, PROJECTS-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md) ("Scope tables denormalise ..." in Data)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (`set_config(..., true)`, fail-closed policies, roles)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/access/data-model.md) (`role_assignment`)

## Spec

Enforce project scope in Postgres as well as in `PolicyService`: a denormalised scope table maintained by triggers, a restrictive RLS predicate on project-scoped tables, and property tests proving the two layers agree.

- **files**:
  - db/migrations/<timestamp>_access_scope_rls.sql
  - db/templates/project-scoped-policy.sql
  - apps/api/src/modules/access/scope/with-principal.ts
  - apps/api/src/modules/access/scope/run-as-system.ts
  - apps/api/src/modules/access/api.ts
  - apps/api/src/modules/access/tests/scope/
  - tests/access/policy-rls-parity.spec.ts
  - tests/access/project-scope-coverage.spec.ts
- **steps**:
  - 1. Migration. Table `access_user_scope`: tenant_id, user_id, scope_kind (`tenant`|`project`), project_id NULL, role_assignment_id FK ON DELETE CASCADE, valid_from, valid_to, FORCE RLS on tenant, index (tenant_id, user_id, project_id). An AFTER INSERT/UPDATE/DELETE trigger on `role_assignment` maintains it (soft-delete removes the row). Backfill it from existing assignments in the same migration.
  - 2. In the same migration, add STABLE functions `app_user_id()` (`nullif(current_setting('app.user_id', true), '')::uuid`) and `app_principal_kind()`, and `access_project_visible(p_project uuid) RETURNS boolean`. That function returns true when the principal kind is `system` or `api_client` (tenant-wide by design), or when an `access_user_scope` row exists for `app_user_id()` with `scope_kind='tenant'` or the given project, and `valid_from <= now()` and `valid_to` is null or later than now. Validity is checked at query time.
  - 3. Add RESTRICTIVE policies `FOR ALL TO aip_app USING (...) WITH CHECK (...)`: on `projects` using `access_project_visible(id)` and on `sites` using `access_project_visible(project_id)` (both tables from PROJECTS-01). Add `db/templates/project-scoped-policy.sql`, which every later table with a `project_id` copies, together with an index on (tenant_id, project_id).
  - 4. `withPrincipal(principal, fn)` wraps `withTenant` and, in the same transaction, runs parameterised `set_config('app.user_id', $1, true)` and `set_config('app.principal_kind', $2, true)`. The request pipeline uses it after the session guard. `runAsSystem(tenantId, fn)` sets kind `system` for worker jobs. A dependency-cruiser rule allows importing it only from `apps/worker` and `apps/api/src/platform`. With no user set, project-scoped tables return no rows (fail closed).
  - 5. Parity property test (`fast-check`, 200 runs) in `tests/access/policy-rls-parity.spec.ts`. Generate a tenant with 3 projects, 4 users and random assignments (tenant or project scope, random default roles, validity windows around now). For every user and project assert: (a) if `PolicyService.can(user, X, {projectId})` is allowed for any X, the project row is visible under RLS; (b) if the project row is visible under RLS, the user has an active assignment covering that project.
  - 6. Coverage test `tests/access/project-scope-coverage.spec.ts`. Scan `pg_catalog`; every table with a `project_id` column must have a restrictive policy calling `access_project_visible`, unless it is listed in `schema_convention_exceptions` (DATABASE-01).
- **acceptance**:
  - A user assigned only to P1 sees only P1's projects and sites rows at the database level, even through a query with no WHERE clause.
  - With no `app.user_id`, project-scoped tables return 0 rows.
  - The policy/RLS parity property holds across 200 generated cases.
  - A new table with `project_id` but no scope policy fails CI.
- **tests**:
  - **unit**:
    - `setConfigStatements({kind:'user', userId:'u1', tenantId:'t1'})` returns parameterised `set_config` calls for `app.tenant_id`, `app.user_id` and `app.principal_kind`, all with `is_local = true`.
    - `withPrincipal` with an api_client principal sets `app.principal_kind` to `api_client` and does not set `app.user_id`.
  - **integration**:
    - Testcontainers. User u assigned to P1 only: `SELECT id FROM projects` returns [P1]. A tenant-scope user gets [P1, P2, P3].
    - Tenant set but `app.user_id` unset: `SELECT count(*) FROM projects` returns 0.
    - u inserts a site into P2. Expected: error `new row violates row-level security policy`.
    - An assignment with `valid_to = now() + 1s`; wait 2 s and select. Expected: 0 rows.
    - `runAsSystem(tenantA)` selects all three projects. In the same test, tenant B's projects stay invisible.
    - Soft-delete u's role_assignment. Expected: the `access_user_scope` row is removed and the SELECT returns 0 rows.
    - A fixture table `widgets(project_id uuid)` with no policy makes the coverage test fail with `table widgets has project_id but no project scope policy`.
    - The parity property passes 200 runs. With the trigger disabled as a seeded fault, it fails.
  - **e2e**:
    - Playwright on compose: alice (inspector on P1 only) opens the projects register. Expected: only P1 is listed. Navigating directly to `/projects/<P2 id>` shows the not-found page, and `GET /api/v1/projects/<P2 id>` returns 404.
