# ENT-03 — Billing state and enforcement (ADR 0023)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ENT-01, TENANCY-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. ADRs: [0023](../../docs/adr/0023-operator-entitlement-controls-and-delinquency.md), [0015](../../docs/adr/0015-tenant-row-and-tenant-resolution.md), [0008](../../docs/adr/0008-entitlements-and-commercial-model.md), [0010](../../docs/adr/0010-signoff-assurance.md)

## Spec

Add a per-tenant billing state that an operator moves with a reason, and enforce it on every request.

- **files**:
  - apps/api/migrations/versions/<rev>_tenant_billing_state.py
  - apps/api/aip/modules/tenancy/billing_state.py
  - apps/api/aip/modules/tenancy/routes.py (operator routes)
  - apps/api/aip/modules/tenancy/tests/test_billing_state.py
- **steps**:
  - 1. Table `tenant_billing_state` (tenant table template, FORCE RLS): state (`good_standing`, `past_due`, `restricted`, `suspended`), `past_due_since`, `grace_until`, `bridge_features` (jsonb) and `bridge_until`, `reason`, `updated_by`, timestamps; append-only history table for every move.
  - 2. Enforce in `require_active_tenant`: `good_standing` and `past_due` pass (with a banner flag for users who may manage billing); `restricted` allows read, export and billing routes for users holding the billing permission and refuses everyone else with 403 `TENANT_RESTRICTED`; mutations other than billing are refused; `suspended` returns the existing `TENANT_SUSPENDED`. A valid bridge lets the named feature through.
  - 3. Operator routes (platform operator, reason required): move state, extend grace, set or clear a bridge, restore to good standing. Each writes an audit event and bumps the entitlement version.
  - 4. A daily job lists tenants past their grace and notifies operators. It never changes a state itself.
  - 5. Sync while `restricted` accepts records signed before the restriction time and refuses new ones (proposed in ADR 0023 point 12).
- **acceptance**:
  - Only an operator can move the state, and only with a reason.
  - A `restricted` tenant can export reports and pay; an inspector gets 403 and the device keeps its queue.
  - No state change deletes data.
- **tests**:
  - **integration**:
    - Move a tenant to `restricted`. Expected: a billing admin can read and export; a field user gets 403 `TENANT_RESTRICTED`; a POST to create an inspection by the admin is refused.
    - A bridge for report export until tomorrow. Expected: export works for a restricted tenant's non-billing user, and stops after the bridge date.
    - The daily job over a tenant 15 days past due. Expected: one operator notification, state unchanged.
    - Restore to good standing. Expected: the next request from every user succeeds with no re-login.
