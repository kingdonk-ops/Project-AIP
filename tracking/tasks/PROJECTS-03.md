# PROJECTS-03 — Project membership, header switcher, X-Project-Id enforcement

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`projects`](../../docs/blueprint/modules/projects/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-02, ARCH-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/projects/README.md`](../../docs/blueprint/modules/projects/README.md)
3. ADRs: 0002 (`withTenant`, RLS policy form), 0004 (layout), 0005 (cookie sessions)
4. Only if the step needs it: the `project_members` table in [`data-model.md`](../../docs/blueprint/modules/projects/data-model.md) and the `/projects/:id/people` section of [`routes.md`](../../docs/blueprint/modules/projects/routes.md)

## Spec

Make project scoping the platform default. Users are members of projects, the header switcher picks the current project, and the API honours `X-Project-Id` only for projects the caller belongs to (or for holders of the tenant-wide override).

- **files**:
  - db/migrations/<timestamp>_project_members.sql
  - apps/api/src/modules/projects/membership.service.ts
  - apps/api/src/modules/projects/membership.controller.ts
  - apps/api/src/modules/projects/project-membership.resolver.ts
  - apps/api/src/modules/projects/api.ts
  - apps/api/src/modules/projects/permissions.ts
  - apps/api/src/modules/projects/tests/
  - apps/web/src/features/projects/ProjectSwitcher.tsx
  - apps/web/src/features/projects/__tests__/
- **steps**:
  - 1. Write a migration from the tenant-table template for `project_members`: id, tenant_id, project_id (FK projects), user_id, default_role_id (nullable), starts_on, ends_on (nullable), last_selected_at (nullable), created_at, updated_at, deleted_at. Add unique (tenant_id, project_id, user_id) WHERE deleted_at IS NULL and an index on (tenant_id, user_id). Use FORCE RLS with the ADR 0002 policy.
  - 2. In membership.service.ts, add a member by inserting the row and calling ACCESS-02's published `assignRole(userId, roleId, {projectId})` in the same `withTenant` transaction. When no role is given, use the project default role from ACCESS-02's seed. Removing a member soft-deletes the row and revokes that user's project-scoped assignments in the same transaction. Emit `project.member_added` and `project.member_removed`.
  - 3. Add the endpoints: GET/POST `/api/v1/projects/:id/members` and DELETE `/api/v1/projects/:id/members/:userId`, guarded by `project.members.manage` (list needs only `project.view`). Add GET `/api/v1/me/projects`, which returns the caller's active memberships ordered by last_selected_at desc, and PUT `/api/v1/me/current-project` with `{projectId}`, which sets last_selected_at and returns 404 for non-members.
  - 4. In project-membership.resolver.ts, implement the injectable resolver that ARCH-04's context middleware calls for `X-Project-Id`. It returns true only if the caller has an active membership (today between starts_on and ends_on, and not soft-deleted) or holds the tenant-level permission `project.view_all`. Cache the answer per request only.
  - 5. Enforce scoping by default. When `X-Project-Id` is present and allowed, the context's projectId is set and project-scoped lists filter by it. When it is absent, list endpoints in this module return only member projects, unless the caller has `project.view_all` and sends `?scope=all`. Expose `ProjectsApi.assertMember(ctx, projectId)` and `ProjectsApi.memberProjectIds(ctx)` from api.ts for later modules.
  - 6. Build ProjectSwitcher.tsx for the shell header slot from DESIGN-02. It lists `/api/v1/me/projects`, shows code (mono) and name, and searches with type-ahead. Selecting a project calls PUT current-project, stores the id for the generated client so every request sends `X-Project-Id`, and refreshes the route. "All projects" is offered only with `project.view_all`. The keyboard and screen-reader behaviour comes from the ui package's combobox.
  - 7. Declare `project.members.manage` and `project.view_all` in permissions.ts and the manifest, and regenerate the API client.
- **acceptance**:
  - A request with `X-Project-Id` for a project the user is not a member of gets 403 `PROJECT_SCOPE_DENIED`, and no handler code runs.
  - A tenant admin with `project.view_all` can use any project id, and can see all projects with `?scope=all`.
  - The switcher remembers the last project across logins (server-side last_selected_at, not localStorage).
  - Adding and removing a member is atomic with the ACCESS-02 role assignment: a failure in either rolls back both.
- **tests**:
  - **unit**:
    - The resolver returns true for membership `{starts_on:'2026-01-01', ends_on:null}` on 2026-10-07, false for `{ends_on:'2026-09-30'}`, and true for a non-member holding `project.view_all`.
    - ProjectSwitcher with 3 memberships renders them in last_selected order. Typing "KIPS" filters the list to 1 item.
  - **integration** (Testcontainers):
    - User U is a member of P1 only. GET `/api/v1/projects` with `X-Project-Id: P2`. Expected: 403 `PROJECT_SCOPE_DENIED`. With `X-Project-Id: P1`. Expected: 200.
    - GET `/api/v1/projects` as U without the header. Expected: only P1. As an admin with `project.view_all` and `?scope=all`. Expected: P1 and P2.
    - Make ACCESS-02's assignRole throw inside POST members. Expected: 500, with no `project_members` row and no role assignment.
    - DELETE the member, then repeat the P1 request. Expected: 403.
    - PUT current-project with tenant B's project id while acting as tenant A. Expected: 404.
  - **e2e** (Playwright):
    - Log in as a user who is a member of two projects and pick the second one in the header switcher. Expected: the header shows its code, and after a logout and login the same project is still selected.
