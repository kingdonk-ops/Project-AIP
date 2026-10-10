# TENANCY-05 — Tenant settings, modules and provisioning

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ENT-01, IDENTITY-04, TENANCY-01, TERMS-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Create tenants repeatably with region, terminology set and admin invite.

- **depends on**:
  - TENANCY-01
  - ARCH-08
- **files**:
  - migrations/versions/0150_tenant_settings_modules.sql
  - apps/api/src/modules/tenancy/provisioning.service.ts
  - apps/api/src/modules/tenancy/settings.controller.ts
  - apps/web/src/features/tenancy/ProvisioningWizard.tsx
- **steps**:
  - 1. Migration for tenant_settings (branding, retention defaults, quota defaults) and tenant_modules (module, enabled).
  - 2. Provisioning runs in one transaction: create the tenant, seed the template pack, load the en-AU terminology set, create the settings row and queue the admin invite.
  - 3. The region is immutable after provisioning.
  - 4. Build the operator-only wizard at /platform/tenants/new and the tenant settings page at /settings/tenant.
  - 5. Emit tenant.provisioned.
- **acceptance**:
  - A failed seed step leaves no tenant row.
  - Provisioning is idempotent on slug.
  - Region cannot be edited afterward.
- **tests**:
  - **e2e**:
    - As platform operator, complete the wizard for a new tenant. Expected: the tenant appears in /platform/tenants with status active. A tenant admin cannot open /platform/tenants (403).
  - **integration**:
    - Provision tenant 'acme' with the en-AU pack. Expected: tenant, settings, module rows, terminology entries and 1 queued invite exist.
    - Force the seed step to fail. Expected: 0 tenant rows.
    - Provision 'acme' twice. Expected: the second call returns 409 and creates no extra rows.
  - **unit**:
    - Slug 'Kaefer WA' normalises to 'kaefer-wa'.
    - Updating the region on an existing tenant throws ImmutableFieldError.

## Added by ADR 0017 (2026-10-10)

- The wizard takes `contract_ref` (and plan code, term, start and renewal dates, seat limits) and writes
  `tenant_subscription` through ENT-01's service in the same transaction. A production term without `contract_ref`
  is refused; `trial` and `sandbox` may omit it. A contract webhook may pre-fill the form (ENT-02) but never
  provisions a tenant.
- Test: provision with `annual` and no `contract_ref` returns 422 and creates no rows; with `contract_ref`
  creates the tenant and the subscription together.
- Operator routes stay under `/platform/*`; their separate origin is OPS-12.
