# TENANCY-01 — Tenants, regions, fixture tenants and tenant resolution
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02, IDENTITY-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (no AIP data: fixture tenants only), [0002](../../docs/adr/0002-data-access-and-migrations.md) (`with_tenant`, policies), [0004](../../docs/adr/0004-repository-layout.md) (module layout), [0005](../../docs/adr/0005-identity-architecture.md) (tenant comes from the app-issued credential, not a raw Keycloak claim; `login_directory` is IDENTITY-01), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (`kms_key_ref`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Introduce `tenants` and `deployment_regions`, seed two fixture tenants for dev/CI/staging, and resolve the request's tenant from the verified app credential into the request context, rejecting inactive tenants.

- **depends on**:
  - DATABASE-02
- **files**:
  - apps/api/migrations/versions/<rev>_tenancy_tenants_regions.py
  - apps/api/aip/modules/tenancy/__init__.py (exports `api` only)
  - apps/api/aip/modules/tenancy/api.py
  - apps/api/aip/modules/tenancy/tables.py
  - apps/api/aip/modules/tenancy/schemas.py
  - apps/api/aip/modules/tenancy/repository.py
  - apps/api/aip/modules/tenancy/service.py
  - apps/api/aip/modules/tenancy/dependencies.py (FastAPI dependency `require_active_tenant`)
  - apps/api/aip/modules/tenancy/routes.py (`GET /api/v1/me/tenant`)
  - apps/api/aip/modules/tenancy/seed.py
  - apps/api/aip/modules/tenancy/manifest.toml
  - apps/api/aip/modules/tenancy/tests/
- **steps**:
  - 1. Revision (raw SQL): `deployment_regions` (code PK, label_key, in_country_only bool; global reference table, allow-listed in TESTING-02) and `tenants` (id uuid PK — the tenant id, name, slug unique, deployment_shape `pooled|siloed`, region_code FK, kms_key_ref text NULL until TENANCY-05 provisioning creates the per-tenant key, status `provisioning|active|suspended|offboarding|offboarded`, timestamps, deleted_at). Enable and FORCE RLS on `tenants` with policy `id = NULLIF(current_setting('app.tenant_id', true), '')::uuid` (USING and WITH CHECK). Declare matching `Table` objects in `tables.py`.
  - 2. Seed regions `ap-southeast-2`, `eu-west-2` and `ap-southeast-1` in the revision (reference data). `seed.py` (`uv run python -m aip.modules.tenancy.seed`, refuses to run when `AIP_ENV=production`) upserts two fixture tenants as the owner: `kaefer-demo` (name "Kaefer Demo", region ap-southeast-2, active) and `tenant-b` (name "Tenant B", region ap-southeast-2, active), with fixed UUIDv7 ids exported as constants for tests and e2e. No data is read from AIP.
  - 3. `require_active_tenant` reads `tenant_id` from the authenticated principal placed in the request context by identity (session row for staff/field/portal, ES256 JWT `tid` for API clients, per ADR 0005). Until IDENTITY lands, tests inject a fake principal. It validates the uuid, loads the tenant inside `with_tenant`, and stores `tenant_id`, `slug` and `region_code` in the request context (ARCH-04's context if merged).
  - 4. Map status to access: `active` allows; `suspended` → 403 `TENANT_SUSPENDED`; `offboarding`/`offboarded` → 403 `TENANT_OFFBOARDED`; `provisioning` → 403 `TENANT_NOT_READY`. No principal or no tenant → 401.
  - 5. `api.py` exports only `get_tenant(tenant_id)`, `require_active_tenant` and the `TenantView` Pydantic model; other modules import nothing else from tenancy (import-linter).
- **acceptance**:
  - A request with no authenticated principal, or a principal without a tenant, gets 401 before any tenant query.
  - A suspended tenant gets 403 on every tenant-scoped route.
  - `tenants` is visible to `aip_app` only for the caller's own row.
  - No code path reads AIP data; fixture tenants come only from `seed.py`.
- **tests**:
  - **e2e**:
    - Log in as `admin@kaefer-demo.test` through Keycloak (compose stack). Expected: `GET /api/v1/me/tenant` returns slug `kaefer-demo` and region `ap-southeast-2`.
  - **integration** (pytest + testcontainers-python, after `seed.py`):
    - As `aip_app` inside `with_tenant(kaefer_demo_id)`: `SELECT * FROM tenants`. Expected: exactly 1 row, slug `kaefer-demo`.
    - Set `tenant-b` to suspended and call a fixture route guarded by `require_active_tenant` as a tenant-b principal (httpx `AsyncClient` on the app). Expected: 403 with code `TENANT_SUSPENDED`.
    - Run `seed.py` twice. Expected: still 2 tenants and 3 regions.
  - **unit**:
    - `require_active_tenant` maps principal `tenant_id` to the context and rejects `"not-a-uuid"` with 401.
    - The status map: `active` allows; `suspended`, `offboarding`, `offboarded` and `provisioning` deny with their codes.
    - `seed.main()` with `AIP_ENV=production` exits non-zero without connecting.
