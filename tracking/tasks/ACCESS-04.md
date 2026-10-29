# ACCESS-04 — Teams, membership, cache-invalidation event

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: converted to Python backend per ADR 0001 -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-02, ARCH-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox and dispatcher), [0002](../../docs/adr/0002-data-access-and-migrations.md), [0020](../../docs/adr/0020-role-management-and-guardrails.md) (access version), [0030](../../docs/adr/0030-outbox-dispatch-semantics.md), [0037](../../docs/adr/0037-project-scope-rls-and-sites.md) (`access_user_scope`)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/access/data-model.md) (`team`, `team_member`)

## Spec

Add teams and team membership, let a role be assigned to a whole team, and keep a versioned cross-request policy cache that the `team.membership_changed` and `access.grants_changed` events invalidate on every API instance.

- **files** (Python backend, ADR 0001):
  - apps/api/migrations/versions/<timestamp>_access_teams.py (Alembic raw SQL from `db/templates/tenant_table.sql.tpl`)
  - apps/api/aip/modules/access/tables.py (declare `team`, `team_member`; `role_assignment.user_id` nullable)
  - apps/api/aip/modules/access/teams/{repository,service,routes,schemas}.py
  - apps/api/aip/modules/access/policy_cache.py
  - apps/api/aip/modules/access/roles/grant_provider.py, roles/repository.py, roles/service.py, roles/schemas.py
  - apps/api/aip/modules/access/events.py (events and the `user.deactivated` subscriber; manifest `events`/`subscribes`)
  - apps/api/aip/modules/access/api.py (published interface)
  - apps/api/aip/modules/access/tests/teams/
- **steps**:
  - 1. Migration (tenant template, FORCE RLS). Table `team`: id, tenant_id, organisation_id NULL, project_id NULL, name, team_type (`internal`|`subcontractor`|`client`), scim_group_id NULL, timestamps, deleted_at, with UNIQUE (tenant_id, project_id, lower(name)) WHERE deleted_at IS NULL, treating NULL project_id as one bucket. Table `team_member`: tenant_id, team_id, user_id, source (`manual`|`scim`), timestamps, deleted_at, with UNIQUE (team_id, user_id) WHERE deleted_at IS NULL. Make `role_assignment.user_id` nullable and add an FK on `team_id` plus CHECK: `scope_type='team'` requires team_id and a null user_id; every other scope requires user_id. Extend ACCESS-03's `access_user_scope` trigger so team assignments and membership changes keep a row for every active member, scoped to the team's project (or `tenant` if the team has no project).
  - 2. Teams API (`access.team.manage`; a project-level team may also be managed by holders of that permission on the team's project; checked in the service through `PolicyService`). `GET|POST /api/v1/access/teams`, `PATCH|DELETE /api/v1/access/teams/{team_id}`, `GET|POST /api/v1/access/teams/{team_id}/members {userIds[]}`, `DELETE /api/v1/access/teams/{team_id}/members/{user_id}`. A duplicate name returns 409 `TEAM_NAME_TAKEN`. Enable `{type:'team', teamId}` in the ACCESS-02 assignments API.
  - 3. `RoleGrantProvider` resolves team assignments through active memberships: a member gets the role's permissions at the team's project scope, or tenant scope if the team has no project.
  - 4. `policy_cache.py` keeps a per-user version and a tenant version in Redis (built with the TENANCY-02 `redis_key` builder: `tenant:<tenant>:access:ver:<userId>` and `tenant:<tenant>:access:ver`), and caches resolved grants for 5 minutes under (user, userVersion, tenantVersion). Every write that changes grants emits, in the same transaction, the outbox event `team.membership_changed {teamId, userIds, change}` or `access.grants_changed {userIds | null}` (null means the whole tenant), including the ACCESS-02 role and assignment writes. After commit the writing request bumps the versions itself (read-your-writes). An ARCH-07 subscriber bumps them again for other instances and for any missed bump.
  - 5. Subscriber on `user.deactivated` (IDENTITY-05): soft-delete the user's team memberships and role assignments and bump their version.
  - 6. Export `list_team_members(conn, team_id)` and `teams_for_user(conn, user_id)` from `api.py` for approval routes (APPROVALS-04).
- **acceptance**:
  - Assigning a role to a team gives every current member that role. Removing a member takes it away on the member's next request, on any API instance.
  - No cached decision survives a grant change for longer than one dispatcher cycle, and the instance that made the change sees it immediately.
  - A deactivated user loses all team memberships.
- **tests**:
  - **unit**:
    - `version_key(t1, u1)` returns `tenant:<t1>:access:ver:<u1>` (the TENANCY-02 builder's form).
    - `resolve_grants` with a team assignment of `inspector` on team T (project P1) gives a member a project grant on P1, and gives a non-member nothing.
    - The CHECK-mirroring Pydantic schema rejects `{type:'team'}` together with a userId.
  - **integration** (real Postgres, Testcontainers):
    - Add u to team T (with `inspector` assigned on P1). Expected: `can(u, 'project.view', Resource(project_id=P1))` is true. Remove u. Expected: false on the next call, not stale.
    - Create two teams with the same name in the same project. Expected: 409 `TEAM_NAME_TAKEN`.
    - After adding a member, the outbox has a `team.membership_changed` row with userIds `[u]`.
    - Dispatch `user.deactivated` for u. Expected: u's `team_member` rows have `deleted_at` set.
    - Two app instances share Redis and Postgres. Remove a membership through instance 1 (its own bump lost) and run the dispatcher once. Expected: instance 2's `can()` returns false.
    - A team member can select P1's `projects` row under RLS (scope row created from the team).
    - Tenant B adds a tenant A user to a team. Expected: 404.
  - **e2e**: carried to the Teams UI task (no user-facing page in this task; ACCESS-05 builds Settings > Teams).
