# ACCESS-01 — Permission catalogue from manifests + PolicyService.can + Nest guard (deny by default)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`access`](../../docs/blueprint/modules/access/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-02, ARCH-04, IDENTITY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/access/README.md`](../../docs/blueprint/modules/access/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/permissions`, manifests), [0005](../../docs/adr/0005-identity-architecture.md) (principal kinds), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/access/data-model.md) (table `permission`)

## Spec

Build one deny-by-default authorisation layer: a permission catalogue assembled from module manifests, an in-process `PolicyService.can(principal, action, resource)` fed by pluggable grant providers, and a global Nest guard that refuses any route without an explicit access declaration.

- **files**:
  - db/migrations/<timestamp>_access_permission_catalogue.sql
  - apps/api/src/modules/access/manifest.json
  - apps/api/src/modules/access/catalogue/catalogue.ts
  - apps/api/src/modules/access/catalogue/catalogue-sync.ts
  - apps/api/src/modules/access/policy/policy.service.ts
  - apps/api/src/modules/access/policy/grant-provider.ts
  - apps/api/src/modules/access/policy/decorators.ts
  - apps/api/src/modules/access/policy/access.guard.ts
  - apps/api/src/modules/access/abilities.controller.ts
  - apps/api/src/modules/access/api.ts
  - packages/permissions/src/catalogue.generated.ts
  - tools/gen-permissions.ts
  - apps/api/src/modules/access/tests/
- **steps**:
  - 1. Each manifest permission entry is `{code, description, privileged?}`. The code must match `^<moduleId>\.[a-z][a-z0-9_]*\.(read|create|update|delete|approve|sign|manage|export)$`. `catalogue.ts` builds the catalogue from the ARCH-02 registry at boot. An invalid or duplicate code stops boot with a message naming the module and code.
  - 2. Migration for the global reference table `permission`: code text PK, module_id, description, is_privileged bool, deprecated_at timestamptz NULL, updated_at. It has no tenant_id and no RLS, and `aip_app` gets SELECT only. Writes go only through SECURITY DEFINER `access_sync_permissions(p_catalogue jsonb)`, which upserts the codes and sets `deprecated_at` on codes that are no longer declared (never deletes). `catalogue-sync.ts` calls it once at boot.
  - 3. `tools/gen-permissions.ts` writes `packages/permissions/src/catalogue.generated.ts`, containing a `PermissionCode` string-literal union and a `PERMISSIONS` const with the privileged flags, for typed use in the API and web. A CI step fails if regenerating changes the file.
  - 4. `PolicyService.can(principal, action, resource?)` returns `Decision {allowed, reason:'granted'|'no_grant'|'unknown_permission'|'inactive_principal'|'provider_error', matchedGrant?}`. Grants come from registered `GrantProvider`s (their union); each grant is `{permission, scope:{type:'tenant'} | {type:'project', projectId}}`. Matching rules: a tenant grant matches any resource in the principal's tenant; a project grant matches only when `resource.projectId` is equal; a resource without a projectId matches only tenant grants; any other scope type never matches (fail closed). An unknown action is denied and logged. A provider that throws gives a denial. An `api_client` principal (IDENTITY-06) is allowed exactly when the action is in its scopes. Grants are memoised per request only; ACCESS-04 adds the cross-request cache. Also export `assertCan` (throws 403 `{code:'FORBIDDEN', permission}`) and `filterAllowed`.
  - 5. Decorators `@Public()` (no session), `@Authenticated()` (session, no permission) and `@Requires(code, {resource?: (req) => Resource})`. The global `access.guard.ts` runs after IDENTITY's session guard. A route with none of the three is denied at runtime, and a boot check (Nest DiscoveryService) fails boot listing every such route. `@Requires` with a code not in the catalogue also fails boot.
  - 6. `GET /api/v1/access/me/abilities?projectId=` (`@Authenticated`) returns `{permissions: PermissionCode[]}`, which the UI uses to hide actions. Add `access.role.read`, `access.role.manage` (privileged), `access.role_assignment.read`, `access.role_assignment.manage` (privileged), `access.team.manage` and `access.matrix.export` to the access manifest.
- **acceptance**:
  - Every route carries `@Public`, `@Authenticated` or `@Requires`. Otherwise boot fails, and the route is denied at runtime.
  - With no grant provider registered, every `@Requires` route returns 403.
  - The `permission` table mirrors the manifests, and removed codes are deprecated, never deleted.
  - `packages/permissions` is regenerated deterministically and CI catches drift.
- **tests**:
  - **unit**:
    - `can(user with tenant grant 'assets.asset.read', 'assets.asset.read', {projectId:'p1'})` is allowed.
    - A project grant on p1 checked against a resource in p2 is denied with `no_grant`.
    - A project grant checked against a resource with no projectId is denied.
    - A grant provider that throws gives a denial with `provider_error`.
    - `can(..., 'ghost.thing.read')` is denied with `unknown_permission`.
    - Manifest code `Assets.Read` fails validation.
    - An api_client with scopes `['assets.asset.read']` is allowed `assets.asset.read` and denied `assets.asset.create`.
  - **integration**:
    - Boot with a fixture module whose controller has an undecorated `GET /api/v1/fixture/unguarded`. Expected: boot fails and the error contains `GET /api/v1/fixture/unguarded`.
    - A fixture manifest declaring `fixture.item.read` twice. Expected: boot fails with `duplicate permission fixture.item.read`.
    - Boot with `{fixture.item.read, fixture.item.create}`, then reboot without `fixture.item.create`. Expected: that row still exists with `deprecated_at` set.
    - As `aip_app`, `INSERT INTO permission ...`. Expected: permission denied.
    - A fixture route with `@Requires('fixture.item.read')` called by a principal with no grants. Expected: 403 `{code:'FORBIDDEN', permission:'fixture.item.read'}`. With a fake provider granting it. Expected: 200.
    - Run `gen-permissions` twice. Expected: identical output.
  - **e2e**:
    - Playwright on compose: signed-in alice with no roles calls `GET /api/v1/me`, which returns 200 (`@Authenticated`). `GET /api/v1/access/me/abilities` returns 200 `{permissions:[]}`. A `@Requires` route returns 403.
