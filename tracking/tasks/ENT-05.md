# ENT-05 — Usage sources and project toggles for entitlements

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) (with identity, uploads, projects) |
| Phase | P0 |
| Size | S |
| Depends on | ENT-01, UPLOADS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. ADRs: [0008](../../docs/adr/0008-entitlements-and-commercial-model.md), [0023](../../docs/adr/0023-operator-entitlement-controls-and-delinquency.md)
3. `apps/api/aip/modules/tenancy/entitlements/usage.py` and `service.py` (the `UsageSource` and
   `ScopeToggleProvider` protocols ENT-01 left empty)

## Spec

ENT-01 built the registries but no module plugs into them yet, so "Plan and usage" shows 0 seats and 0
storage used, and `check_seat` always sees 0 active users. Fill them in, each module through
`aip.modules.tenancy.api` only.

- **steps**:
  - 1. identity registers a `UsageSource` that counts active members per user class (`staff`, `field`,
    `portal`) for the tenant, and calls `EntitlementService.check_seat` when a membership is activated
    (`OVERAGE` allows and records; never lock a user out mid-shift).
  - 2. uploads registers a `UsageSource` for released stored bytes (after UPLOADS-02 adds `stored_files`), and
    calls `ensure_within_limit(..., "limit.storage_gb", ...)` before presigning a new upload (403
    `LIMIT_REACHED` at 100%; reads, exports and sign-off never check).
  - 3. projects registers a `ScopeToggleProvider` once project feature toggles exist (they can only switch a
    feature off), and counts active projects for `limit.projects`.
  - 4. OPS-13 schedules `python -m aip.modules.tenancy.entitlements.snapshot_cli` daily with the tenant list
    (it estimates database size only on Sundays and at month end).
  - 5. When AUDIT-01 lands, make sure the database-size estimate counts `audit_log` (the estimate only counts
    tables the runtime role can read; give it a definer function or a grant if the audit role hides them).
- **acceptance**:
  - The plan-and-usage page shows real seats per class and storage; the monthly snapshot records them.
- **tests**:
  - **integration**: two tenants with known members and files produce their own counts only; activating one
    member over the full-seat limit records an overage; a presign at 100% storage is 403 `LIMIT_REACHED`.
