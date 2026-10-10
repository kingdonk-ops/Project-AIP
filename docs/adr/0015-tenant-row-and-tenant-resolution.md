# ADR 0015: The tenant row, fixture tenant ids and tenant resolution errors

- **Status:** proposed
- **Date:** 2026-10-08
- **Affects:** tenancy, identity, platform context; TENANCY-01, TENANCY-05, IDENTITY-03, TESTING-02

## Context

TENANCY-01 adds `tenants` and `deployment_regions` and the `require_active_tenant` dependency.
A few details were not settled by ADR 0002, ADR 0005 or the task spec:

- `tenants` has no `tenant_id` column (its `id` is the tenant id), so the tenant-table template does
  not fit, and the spec does not say which roles may write it.
- The spec asks for "fixed UUIDv7 ids" for the fixture tenants, but `apps/api/tests/conftest.py`
  and the IDENTITY-01 login-directory seeds already use the shared ids
  `00000000-0000-4000-8000-00000000000a` (`kaefer-demo`) and `...0000000b` (`tenant-b`).
- No error-body convention exists for 401/403 raised from a FastAPI dependency.

## Decision

- **`tenants`**: FORCE RLS with `id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`
  (USING and WITH CHECK). `aip_app` and `aip_readonly` get `SELECT` only: the app can read its own
  tenant and cannot create, change or delete any tenant. Provisioning (TENANCY-05) and seeds write
  as the owner, which FORCE RLS also binds to one tenant per transaction. Slugs are unique for
  ever, also after soft delete, so a slug in `login_directory` cannot be taken over later.
- **`deployment_regions`** is global reference data (code PK, no RLS), `SELECT`-only for runtime
  roles; `label_key` holds a terminology key.
- **Fixture ids** stay the shared ids above (exported as `KAEFER_DEMO_ID` / `TENANT_B_ID` from
  `aip.modules.tenancy.seed`). They are valid UUIDs, and changing them would break the identity
  seeds, the shared test fixtures and the login-directory foreign key for no gain. Production
  tenants get app-generated UUIDv7 ids (ADR 0002).
- **Resolution** fails closed: no principal, or a principal whose tenant id is not a non-nil UUID,
  is rejected with 401 before any tenant query (the context middleware checks the principal; the
  dependency checks again). An unknown or soft-deleted tenant is 401 `TENANT_UNKNOWN`; a tenant
  that is not `active` is 403 (`TENANT_SUSPENDED`, `TENANT_OFFBOARDED`, `TENANT_NOT_READY`, and
  `TENANT_UNAVAILABLE` for any unknown status). The body is `{"detail": {"code", "message"}}` and
  never names the tenant.
- After resolution the request context also carries `tenant_slug` and `region_code`
  (`RequestContext` gains both, `None` until resolved).

## Consequences

- TESTING-02's schema guard must accept `id` as the tenant key of `tenants` and allow-list
  `deployment_regions` and `login_directory`.
- Seeds run in order: `tenancy-seed`, then `identity-seed` (compose does this).
- A later platform-wide error envelope can replace the `detail` wrapper in one place
  (`aip/modules/tenancy/dependencies.py`).

## Added statuses (ADR 0022, 2026-10-10)

- `terminating`: the tenant keeps working during the 30-day export window; the app shows a banner. Resolves as active.
- `quarantined`: 403 `TENANT_QUARANTINED`, no logins; an operator can reactivate within the window.
- Billing states (ADR 0023) are separate from `status`: `past_due` passes with a banner, `restricted` returns 403 `TENANT_RESTRICTED` for everyone except billing managers reading, exporting and paying, and `suspended` is the existing `TENANT_SUSPENDED`.
- `archived`: the tenant's data is a sealed bundle (ADR 0022); the main app returns 403 `TENANT_ARCHIVED` and auditors use the archive area.

