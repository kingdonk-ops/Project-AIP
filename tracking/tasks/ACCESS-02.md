# ACCESS-02 — Roles, default role seed, tenant/project role assignment API

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, PROJECTS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox events)
4. Only if the step needs it: [`docs/blueprint/05-access-matrix.md`](../../docs/blueprint/05-access-matrix.md) (the role × module levels to seed), [`data-model.md`](../../docs/blueprint/modules/access/data-model.md) (`role`, `role_permission`, `role_assignment`)

## Spec

Add roles built from the catalogue, seed the default tenant roles from the access matrix, and let admins assign roles at tenant or project scope through a grant provider that feeds `PolicyService`. This module owns role assignment; TENANCY-03's `user_roles.project_id` is superseded.

- **files**:
  - db/migrations/<timestamp>_access_roles.sql
  - apps/api/src/modules/access/roles/default-roles.ts
  - apps/api/src/modules/access/roles/seed-default-roles.ts
  - apps/api/src/modules/access/roles/roles.service.ts
  - apps/api/src/modules/access/roles/roles.controller.ts
  - apps/api/src/modules/access/roles/assignments.service.ts
  - apps/api/src/modules/access/roles/assignments.controller.ts
  - apps/api/src/modules/access/roles/role-grant-provider.ts
  - apps/api/src/modules/access/events.ts
  - apps/api/src/modules/access/api.ts
  - apps/api/src/modules/access/tests/roles/
- **steps**:
  - 1. Migration (tenant template, FORCE RLS). Table `role`: id, tenant_id, code, name_term_key, name NULL, is_system, timestamps, deleted_at, with UNIQUE (tenant_id, code) WHERE deleted_at IS NULL. Table `role_permission`: tenant_id, role_id, permission_code FK `permission(code)`, UNIQUE (role_id, permission_code). Table `role_assignment`: id, tenant_id, user_id FK app_user, role_id, scope_type CHECK in (`tenant`, `project`, `team`, `asset_subtree`), project_id NULL FK projects, team_id NULL, asset_path ltree NULL, source (`manual`|`scim`|`delegation`), valid_from, valid_to NULL, approved_by NULL, created_by, timestamps, deleted_at. Add a CHECK so that `tenant` scope has a null project_id and `project` scope has a non-null project_id. Index (tenant_id, user_id) and (tenant_id, project_id).
  - 2. `default-roles.ts` holds the 11 tenant roles from `05-access-matrix.md` as data, with stable codes `tenant_admin`, `project_manager`, `qaqc_manager`, `hse_officer`, `supervisor`, `inspector`, `field_worker`, `document_controller`, `client_reviewer`, `subcontractor` and `auditor`. Super Admin belongs to the operator realm, not a tenant, and API Client is covered by IDENTITY-06 scopes. Each role maps module to level (`none`|`view`|`create`|`edit`|`approve`|`admin`), and each level expands cumulatively by action suffix: view gives read; create adds create; edit adds update and delete; approve adds approve and sign; admin adds manage and export. Only codes present in the catalogue are inserted; a matrix module with no catalogue entries is skipped with a log line. Display names use term keys `access.role.<code>.name`.
  - 3. `seedDefaultRoles(tx, tenantId)` is idempotent: it upserts system roles by code and syncs their permissions to the current catalogue. It is exported from `api.ts` for TENANCY-05 provisioning, and the CLI `pnpm access:seed-roles --all-tenants` backfills existing tenants.
  - 4. Roles API (`access.role.read` / `access.role.manage`). `GET /api/v1/access/roles`. `POST` a custom role `{code, name, permissions[]}`. `PATCH` and `DELETE` a custom role; DELETE returns 409 `ROLE_IN_USE` while active assignments exist. `POST /roles/:id/clone`. PATCH or DELETE on a system role returns 409 `SYSTEM_ROLE_IMMUTABLE`.
  - 5. Assignments API (`access.role_assignment.read` / `access.role_assignment.manage`). `GET /api/v1/access/role-assignments?userId=&projectId=`. `POST {userId, roleId, scope:{type:'tenant'} | {type:'project', projectId}, validTo?}`. `DELETE :id` soft-deletes. Team and asset_subtree scopes return 400 `SCOPE_NOT_SUPPORTED` until ACCESS-04 and a later task. The project must exist in the tenant (via the projects `api.ts`), otherwise 404 `PROJECT_NOT_FOUND`, and the user must be active. A role containing any privileged permission can be assigned only by a tenant_admin whose session has `aal=2` (otherwise 403 `STEP_UP_REQUIRED`), and `approved_by` is set to the actor. Removing or expiring the last active tenant_admin returns 409 `LAST_TENANT_ADMIN`.
  - 6. `RoleGrantProvider` turns active assignments (deleted_at null, valid_from ≤ now, valid_to null or > now) into tenant or project grants of their roles' permissions, and is registered with `PolicyService`.
  - 7. Emit outbox events `access.role.changed`, `access.role_assignment.created` and `access.role_assignment.removed` (v1, ARCH-05) in the same transaction, for the audit module.
- **acceptance**:
  - Every tenant has the 11 system roles, matching the access matrix.
  - A project-scoped role grants nothing in other projects. A tenant-scoped role applies to all projects.
  - Privileged roles need a tenant_admin with step-up to assign, and the last tenant_admin cannot be removed.
  - System roles cannot be edited or deleted.
- **tests**:
  - **unit**:
    - `expandLevel('approve', ['read','create','update','delete','approve','sign','manage'])` returns `['read','create','update','delete','approve','sign']`.
    - The matrix gives Inspector `create` on "Inspections, ITPs & hold points", so `inspector` gets `inspections.*.read` and `.create` but not `.approve`.
    - The assignment schema rejects `{type:'project'}` without a projectId (400), and rejects `{type:'team'}` with 400 `SCOPE_NOT_SUPPORTED`.
  - **integration**:
    - Run `seedDefaultRoles` twice for kaefer. Expected: 11 roles, and the same `role_permission` count after both runs.
    - Assign `inspector` on P1 to user u. Expected: `can(u, 'inspections.inspection.create', {projectId:P1})` is true and for P2 is false.
    - A tenant-scope `project_manager`. Expected: allowed on P1 and P2.
    - An assignment with `valid_to` yesterday. Expected: denied.
    - Delete the only tenant_admin assignment. Expected: 409 `LAST_TENANT_ADMIN`.
    - Assign `tenant_admin` with an actor session at `aal=1`. Expected: 403 `STEP_UP_REQUIRED`. With `aal=2`. Expected: 201 and `approved_by` set.
    - `PATCH` system role `inspector`. Expected: 409 `SYSTEM_ROLE_IMMUTABLE`.
    - A tenant B admin posts an assignment for a tenant A user id. Expected: 404.
    - After a successful POST, an outbox row `access.role_assignment.created` exists.
  - **e2e**:
    - Playwright APIRequestContext on compose: the seeded kaefer tenant admin creates projects P1 and P2 (PROJECTS-01 API) and assigns alice `inspector` on P1. Expected: alice's `GET /api/v1/access/me/abilities?projectId=P1` includes `projects.project.read`, the same call for P2 returns an empty list, and `GET /api/v1/projects/P2` as alice returns 403 or 404.
