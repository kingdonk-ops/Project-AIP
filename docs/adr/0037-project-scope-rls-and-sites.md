# ADR 0037: Project-scope RLS, the request principal in the DB, and tenant-scoped sites

- **Status:** accepted (owner, 2026-10-19: sites stay tenant-scoped)
- **Date:** 2026-10-19
- **Affects:** access, projects, database; ACCESS-03, ASSETS-07, and every later task that adds a
  table with a `project_id` record column

## Context

ACCESS-03 enforces project scope in Postgres as well as in `PolicyService`: a denormalised scope
table maintained by a trigger, a restrictive RLS predicate on project-scoped tables, and property
tests proving the two layers agree. The task spec predates the Python backend and the PROJECTS-01
schema, so three things it assumes do not hold and need a recorded decision.

1. **Sites.** The spec says to scope `sites` with `access_project_visible(project_id)`. The
   implemented schema has no `project_id` on `sites`: a site is shared reference data that
   `projects.site_id` points at (many projects to one site), and the blueprint's "sites under
   projects" was not built that way. A project predicate cannot be written on `sites` as it stands.
2. **The principal at the database.** The predicate needs to know who is asking, but nothing set
   `app.user_id`/`app.principal_kind`. A restrictive policy on `projects` fails closed (0 rows, and
   writes rejected) for every caller until the principal is bound.
3. **Where the scope helpers live.** The spec puts `with_principal`/`run_as_system` in the access
   module and has `aip.platform` call them. `aip.platform` must not import `aip.modules` (ARCH-03),
   and only `aip.platform.db` may open connections (ADR 0002), so that placement is impossible.

## Decision

- **Sites are tenant-scoped.** The restrictive project-scope policy goes on `projects` only (keyed
  on its own `id`). `sites` keeps plain tenant isolation. This overrides the spec's `sites` line.
- **`app.user_id` and `app.principal_kind`** are transaction-local settings, set the same way as
  `app.tenant_id` (ADR 0002). `with_tenant` binds them for a `RequestContext` that names a user, so
  every ordinary request handler gets user scope for free. `access_project_visible(p_project)` is
  true for a `system`/`api_client` principal (tenant-wide by design) or when the user has a live
  `access_user_scope` row for the tenant or that project; validity is checked at query time.
- **`with_principal` / `run_as_system` live in `aip.platform.db.scope`**, next to `with_tenant`, and
  are re-exported from `aip.modules.access.api` for other modules. Workers that must see every
  project-scoped row in a tenant use `run_as_system`.
- **`access_user_scope`** denormalises each live tenant/project `role_assignment`, maintained by an
  `AFTER` trigger (a soft-delete of the assignment removes the row). A new table with a `project_id`
  **record** column copies `db/templates/project_scoped_policy.sql`; the coverage test
  (`tests/access/test_project_scope_coverage.py`) fails CI for one that does not. Existing
  `project_id` tables whose column is a scope target or configuration key (e.g. `role_assignment`,
  `term_override`, `upload_sessions`) are listed in `project_scope_allowlist.yaml` with a reason.
- **Backfill is a greenfield no-op.** `role_assignment` is empty when this migration runs (ACCESS-02
  seeds at runtime, after migrations), and a cross-tenant backfill as the `NOBYPASSRLS` migrator is
  not expressible within the migration lint (no `DO` blocks, no session `SET` outside the baseline).
  The trigger denormalises assignments as they are written.

## Consequences

- Project scope is enforced at the database, not only in controllers: a list/search/export that
  forgets a `WHERE` still cannot leak another project's `projects` rows. Creating or seeing all
  projects needs tenant (or system) scope; a project-scoped user sees only their projects.
- Tests and code that read `projects` must bind a principal: request handlers already do through
  `with_tenant(get_context())`; workers use `run_as_system`; tests seed a tenant-scope assignment or
  use `run_as_system` (the PROJECTS-01 and TESTING-09 project tests were updated accordingly).
- ASSETS-07 (asset-subtree scope) builds on `access_user_scope` and the predicate pattern here.
- Hardening the legacy `project_id` tables now allow-listed (uploads, approvals) is follow-up work,
  tracked in those modules rather than widened into this task.
