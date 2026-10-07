# TENANCY-01 — Tenants, regions and tenant resolution

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Introduce the tenants table and derive tenant_id from the verified token.

- **depends on**:
  - DATABASE-02
- **files**:
  - migrations/versions/0105_tenants_regions.sql
  - apps/api/src/modules/tenancy/tenancy.service.ts
  - apps/api/src/modules/tenancy/tenancy.schemas.ts
  - apps/api/src/modules/tenancy/tenant-context.guard.ts
- **steps**:
  - 1. Migration for deployment_regions (code, label, in_country_only) and tenants (slug unique, deployment_shape, region_id, kms_key_ref, status). Protect tenants with the policy id = app.tenant_id.
  - 2. Seed regions ap-southeast-2, eu-west-2 and ap-southeast-1, and the tenant Kaefer, using the existing top-level AIP organisation.
  - 3. Add a guard that reads the tenant claim from the verified token (a Keycloak claim mapper), checks the tenant is active and populates the request context.
  - 4. Reject suspended, offboarding and offboarded tenants with 403.
  - 5. Export only the public service functions from api.ts.
- **acceptance**:
  - A token with no tenant claim gets 401.
  - A suspended tenant gets 403 on every route.
  - The tenants table is visible only for the caller's own row.
- **tests**:
  - **e2e**:
    - Log in as a Kaefer user through Keycloak. Expected: /api/v1/me returns tenant slug 'kaefer' and region ap-southeast-2.
  - **integration**:
    - As app with tenant A set: SELECT * FROM tenants. Expected: exactly 1 row.
    - Set the tenant status to suspended and call GET /api/v1/assets. Expected: 403 with code TENANT_SUSPENDED.
  - **unit**:
    - The guard maps claim tenant_id to the context and rejects a non-uuid claim.
    - The status map: active allows, suspended denies.
