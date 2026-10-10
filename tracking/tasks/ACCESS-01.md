# ACCESS-01 — Permission catalogue from manifests + PolicyService.can + FastAPI access dependencies (deny by default)
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0004](../../docs/adr/0004-repository-layout.md) (`aip/platform/access`, `manifest.toml`, import-linter, `packages/contracts`), [0005](../../docs/adr/0005-identity-architecture.md) (principal kinds), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/access/data-model.md) (table `permission`)

## Spec

Build one deny-by-default authorisation layer in the FastAPI backend: a permission catalogue assembled from module manifests, an in-process `PolicyService.can(principal, action, resource)` fed by pluggable grant providers, and FastAPI access dependencies plus a startup check that refuse any route without an explicit access declaration.

The runtime pieces every module uses live in `aip/platform/access/` (platform never imports modules). The `permission` table, its sync and the abilities route live in the `access` module.

- **files**:
  - apps/api/migrations/versions/<rev>_access_permission_catalogue.py
  - apps/api/aip/platform/access/__init__.py
  - apps/api/aip/platform/access/catalogue.py
  - apps/api/aip/platform/access/policy.py
  - apps/api/aip/platform/access/grants.py
  - apps/api/aip/platform/access/dependencies.py
  - apps/api/aip/platform/access/route_check.py
  - apps/api/aip/platform/access/tests/
  - apps/api/aip/modules/access/manifest.toml
  - apps/api/aip/modules/access/repository.py
  - apps/api/aip/modules/access/service.py
  - apps/api/aip/modules/access/routes.py
  - apps/api/aip/modules/access/schemas.py
  - apps/api/aip/modules/access/api.py
  - apps/api/aip/modules/access/tests/
  - packages/contracts/src/permissions.generated.ts
  - tools/gen_permissions.py
- **steps**:
  - 1. Each `manifest.toml` permission entry is a `[[permissions]]` table `{code, description, privileged = false}`. The code must match `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,2}$` (two or three dot-separated segments, e.g. `project.view`, `audit.activity.view`), and its first segment must be one of the module's declared `permission_namespaces` (manifest field, default `[<module_id>]`). A namespace may be claimed by only one module; a duplicate claim fails startup. `catalogue.py` builds the catalogue from the ARCH-02 module registry when `create_app()` runs. An invalid or duplicate code raises at startup with a message naming the module and code.
  - 2. Alembic revision (raw SQL) for the global reference table `permission`: code text PK, module_id, description, is_privileged bool, deprecated_at timestamptz NULL, updated_at. It has no tenant_id and no RLS, and `aip_app` gets SELECT only. Writes go only through SECURITY DEFINER `access_sync_permissions(p_catalogue jsonb)`, which upserts the codes and sets `deprecated_at` on codes that are no longer declared (never deletes). `modules/access/service.py` calls it once from the app lifespan startup hook.
  - 3. `tools/gen_permissions.py` loads the catalogue (no database needed) and writes `packages/contracts/src/permissions.generated.ts`, containing a `PermissionCode` string-literal union and a `PERMISSIONS` const with the privileged flags, sorted by code, for typed use in the web apps. The abilities response model also types `permissions` as that enum so `packages/api-client` carries it. A CI step fails if regenerating changes the file.
  - 4. `PolicyService.can(principal, action, resource=None)` returns the frozen dataclass `Decision(allowed, reason: Literal['granted','no_grant','unknown_permission','inactive_principal','provider_error'], matched_grant=None)`. Grants come from registered `GrantProvider` `Protocol` implementations (their union); each grant is `Grant(permission, scope=TenantScope() | ProjectScope(project_id))`. Matching rules: a tenant grant matches any resource in the principal's tenant; a project grant matches only when `resource.project_id` is equal; a resource without a project_id matches only tenant grants; any other scope type never matches (fail closed). An unknown action is denied and logged. A provider that raises gives a denial. An `api_client` principal (IDENTITY-06) is allowed exactly when the action is in its scopes. Grants are memoised per request only (on the request context from ARCH-04); ACCESS-04 adds the cross-request cache. Also export `assert_can` (raises `Forbidden`, rendered as 403 `{code:'FORBIDDEN', permission}`) and `filter_allowed`.
  - 5. Access declarations in `dependencies.py`: `public()` (no session), `authenticated()` (session, no permission) and `requires(code, resource=None)` where `resource` is a callable `(Request) -> Resource`. Each is used as `dependencies=[Depends(...)]` on the route and tags the route's dependant with an access marker. `requires` runs after IDENTITY's principal dependency. Install `AccessCheckedRoute` (a custom `APIRoute` class set as the default `route_class`) so a route whose dependant carries no marker returns 403 at runtime. `route_check.py` walks `app.routes` at startup and raises listing every `METHOD path` without a marker, and every `requires` code missing from the catalogue.
  - 6. `GET /api/v1/access/me/abilities?projectId=` (`authenticated()`) returns `{permissions: PermissionCode[]}`, which the UI uses to hide actions. Add `access.role.read`, `access.role.manage` (privileged), `access.role_assignment.read`, `access.role_assignment.manage` (privileged), `access.team.manage` and `access.matrix.export` to the access `manifest.toml`. Add an import-linter contract that `aip.platform.access` imports nothing from `aip.modules`.
- **acceptance**:
  - Every route carries `public()`, `authenticated()` or `requires()`. Otherwise `create_app()` fails, and the route is denied at runtime.
  - With no grant provider registered, every `requires()` route returns 403.
  - The `permission` table mirrors the manifests, and removed codes are deprecated, never deleted.
  - `packages/contracts/src/permissions.generated.ts` is regenerated deterministically and CI catches drift.
- **tests** (pytest; integration uses testcontainers-python Postgres and `httpx.AsyncClient`):
  - **unit**:
    - `can(user with tenant grant 'assets.asset.read', 'assets.asset.read', Resource(project_id='p1'))` is allowed.
    - A project grant on p1 checked against a resource in p2 is denied with `no_grant`.
    - A project grant checked against a resource with no project_id is denied.
    - A grant provider that raises gives a denial with `provider_error`.
    - `can(..., 'ghost.thing.read')` is denied with `unknown_permission`.
    - Manifest code `Assets.Read` fails validation naming the module.
    - An api_client with scopes `['assets.asset.read']` is allowed `assets.asset.read` and denied `assets.asset.create`.
  - **integration**:
    - `create_app()` with a fixture module whose router has an undecorated `GET /api/v1/fixture/unguarded`. Expected: startup raises and the error contains `GET /api/v1/fixture/unguarded`.
    - A fixture `manifest.toml` declaring `fixture.item.read` twice. Expected: startup raises `duplicate permission fixture.item.read`.
    - Start with `{fixture.item.read, fixture.item.create}`, then restart without `fixture.item.create`. Expected: that row still exists with `deprecated_at` set.
    - As `aip_app`, `INSERT INTO permission ...`. Expected: permission denied.
    - A fixture route with `requires('fixture.item.read')` called by a principal with no grants. Expected: 403 `{code:'FORBIDDEN', permission:'fixture.item.read'}`. With a fake provider granting it. Expected: 200.
    - Run `python tools/gen_permissions.py` twice. Expected: byte-identical output.
  - **e2e**:
    - Playwright on compose: signed-in alice with no roles calls `GET /api/v1/me`, which returns 200 (`authenticated()`). `GET /api/v1/access/me/abilities` returns 200 `{permissions:[]}`. A `requires()` route returns 403.

## Added by ADR 0020 (2026-10-10)

- Add a per-tenant **access version** (an integer on the tenant's access settings row) that every role edit, reset, project override and assignment change increments in the same transaction. `PolicyService` may cache grants only under that version, so a change applies on the next request with no logout. Test: grant, check allowed, change the role, check denied on the very next request without re-login.
- Permission flags are atomic and named `<module>.<resource>.<action>`; a module manifest declares them at the granularity in ADR 0020 point 5 (for example inspections: draft create, submit, sign, reopen). A manifest that declares only coarse read and write fails the catalogue check for modules in the permission matrix.
