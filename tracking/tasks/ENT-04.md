# ENT-04 — Operator console pages: entitlement overrides and billing state (ADR 0023)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ENT-03, OPS-12 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. ADRs: [0023](../../docs/adr/0023-operator-entitlement-controls-and-delinquency.md), [0017](../../docs/adr/0017-company-systems-and-contract-link.md)

## Spec

Give platform operators two pages on the operator origin: the plan matrix with a per-tenant override console, and a billing-state panel.

- **files**:
  - apps/web/src/routes/platform/tenants/$tenantId/entitlements.tsx
  - apps/web/src/routes/platform/tenants/$tenantId/billing-state.tsx
  - e2e/web/operator-entitlements.spec.ts
- **steps**:
  - 1. Entitlements page: the plan matrix (read-only, from the plan registry) beside this tenant's effective value, source and any override with its expiry; edit or clear an override with a required reason.
  - 2. Billing-state panel: current state and days past due, buttons for extend grace, restricted, suspended, bridge and restore, each asking for a reason; the history list.
  - 3. All labels through terminology keys; operator pages only under `/platform/*` (OPS-12).
- **acceptance**:
  - An override with no reason cannot be saved; the page shows the plan default, the override and the effective value.
  - Every action appears in the history with the operator and reason.
- **tests**:
  - **e2e**:
    - Operator raises a tenant's project limit by override with an expiry. Expected: the effective value changes, the tenant's plan page shows the new limit, and the history has the entry.
    - Operator moves a tenant to `restricted` and back. Expected: states and reasons are listed, and the tenant admin sees the banner and then the restored page.
