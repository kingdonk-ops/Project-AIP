# ARCH-08 — Record-link service and per-tenant feature flags

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-04, DATABASE-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Link any two records to each other and to an asset, and gate deferred modules per tenant.

- **depends on**:
  - ARCH-04
  - DATABASE-02
- **files**:
  - migrations/versions/0101_record_links_feature_flags.sql
  - apps/api/src/platform/links/links.service.ts
  - apps/api/src/platform/flags/flags.guard.ts
- **steps**:
  - 1. Migration for record_links (id, tenant_id, from_type, from_id, to_type, to_id, asset_id, link_kind, created_by) with a unique key on from, to and kind, and for tenant_feature_flags (tenant_id, flag, enabled).
  - 2. Implement link(from, to, kind), unlink and traverse(record, depth<=5), which uses a recursive CTE and cycle protection.
  - 3. Implement the @RequiresFlag('bim') decorator and guard, returning 404 when the flag is off.
  - 4. Emit a platform.flag.changed event when a flag changes.
  - 5. Add RLS and an isolation test for both tables.
- **acceptance**:
  - The chain defect -> NCR -> repair -> re-inspection is retrievable in order.
  - A cyclic link does not loop forever.
  - A flagged route returns 404 for a tenant with the flag off.
- **tests**:
  - **e2e**:
    - Toggle the BIM flag in per-tenant settings. Expected: the BIM nav item appears and disappears after refresh, and the change shows in the audit feed.
  - **integration**:
    - Link defect D to NCR N to repair R to inspection I. traverse(D). Expected: [N,R,I] with depths 1, 2 and 3.
    - Tenant B calls traverse on tenant A's record id. Expected: empty result.
    - Set flag bim=false. GET /api/v1/bim/models. Expected: 404. Set bim=true. Expected: 200.
  - **unit**:
    - traverse on a->b->c->a with depth 5 returns {a,b,c} with no duplicates.
    - Duplicate link call is idempotent (one row).
