# ARCH-08 — Record-link service and per-tenant feature flags
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-02, ARCH-05, ENT-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md) (record-link service, per-tenant feature flags)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0008](../../docs/adr/0008-entitlements-and-commercial-model.md) (release flags stay separate from entitlements), [0004](../../docs/adr/0004-repository-layout.md)

## Spec

Link any two records to each other and to an asset, and gate deferred modules per tenant with release flags (rollout and kill switch). Entitlements (what a tenant paid for) are ENT-01's `EntitlementService`; this task only leaves a hook for it.

- **depends on**:
  - ARCH-04
  - DATABASE-02
- **files**:
  - apps/api/migrations/versions/<YYYYMMDDHHMM>_record_links_feature_flags.py (raw SQL from `db/templates/` tenant-table template)
  - apps/api/aip/platform/links/tables.py, apps/api/aip/platform/links/service.py
  - apps/api/aip/platform/flags/tables.py, apps/api/aip/platform/flags/service.py, apps/api/aip/platform/flags/dependency.py (`requires_flag`)
  - apps/api/aip/platform/flags/routes.py
  - apps/api/tests/platform/links/test_links.py
  - apps/api/tests/platform/flags/test_flags.py
- **steps**:
  - 1. Migration: `record_links` (id, tenant_id, from_type, from_id, to_type, to_id, asset_id null, link_kind, created_by, created_at, updated_at, deleted_at) with a unique index on `(tenant_id, from_type, from_id, to_type, to_id, link_kind) WHERE deleted_at IS NULL`; `tenant_feature_flags` (id, tenant_id, flag, enabled, updated_by, created_at, updated_at, deleted_at) unique on `(tenant_id, flag) WHERE deleted_at IS NULL`. Both `FORCE ROW LEVEL SECURITY` with the fail-closed `app.tenant_id` policy (`USING` and `WITH CHECK`); `aip_app` gets SELECT, INSERT, UPDATE.
  - 2. `LinkService.link(conn, from_ref, to_ref, kind, asset_id=None)` (idempotent: `INSERT ... ON CONFLICT DO NOTHING`), `unlink` (soft delete) and `traverse(conn, ref, max_depth=5)` using a recursive CTE with a visited-path array for cycle protection, returning `(ref, depth)` ordered by depth. `max_depth` above 5 is rejected.
  - 3. `FlagService.is_enabled(conn, flag)` (missing row = the flag's default from a code-level registry of known flags; unknown flag names raise). `requires_flag("bim")` is a FastAPI dependency that returns 404 when the flag is off. It also calls an `EntitlementCheck` protocol whose default implementation allows everything until ENT-01 replaces it (ADR 0008).
  - 4. `GET /api/v1/settings/flags` (current tenant's flags, used by the web nav) and `PUT /api/v1/settings/flags/{flag}` `{enabled: bool}`, gated by permission `tenant.flags.manage`. A change emits `platform.flag.changed {flag, enabled}` through ARCH-05's `emit` in the same transaction. ARCH-05 is not in Depends on: confirm it is `done` before step 4, or mark this task `blocked`.
  - 5. Add the tenant-isolation test for both tables (two fixture tenants).
- **acceptance**:
  - The fixture chain defect → NCR → repair → re-inspection (record types `fixture_defect`, `fixture_ncr`, `fixture_repair`, `fixture_inspection`) is retrievable in order.
  - A cyclic link does not loop forever.
  - A flagged route returns 404 for a tenant with the flag off.
- **tests**:
  - **unit**:
    - `link(a, b, "follows")` twice inserts one row (second call returns the existing id).
    - `traverse(a, max_depth=6)` raises `ValueError`.
  - **integration** (testcontainers-python, connecting as `aip_app`):
    - Link D → N → R → I. `traverse(D)`. Expected: `[(N,1), (R,2), (I,3)]`.
    - Links a → b → c → a; `traverse(a, max_depth=5)`. Expected: `{b, c, a}` with no duplicates and the query returns.
    - In `with_tenant(B)`, `traverse` on tenant A's record id. Expected: empty list.
    - Set flag `bim=false` for tenant A; `GET /api/v1/_fixtures/bim-probe` (test route with `requires_flag("bim")`). Expected: 404. Set `bim=true`. Expected: 200. Tenant B is unaffected.
  - **e2e**:
    - As the `tenant-a` fixture admin, `PUT /api/v1/settings/flags/bim {"enabled": true}`, then `GET /api/v1/settings/flags`. Expected: `bim: true`, and one `platform.flag.changed` row in `domain_events`. Toggle off; expected `bim: false`. (The nav item behaviour is tested by the web shell task against the generated client.)
