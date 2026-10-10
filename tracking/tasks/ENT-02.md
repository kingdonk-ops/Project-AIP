# ENT-02 — Operator usage export and optional contract intake (ADR 0017)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | ENT-01, TENANCY-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. ADRs: [0008](../../docs/adr/0008-entitlements-and-commercial-model.md), [0017](../../docs/adr/0017-company-systems-and-contract-link.md)
3. [`docs/internal/internal.md`](../../docs/internal/internal.md) section 3 (what crosses the boundary)
4. [`tracking/tasks/ENT-01.md`](ENT-01.md) (`tenant_usage`, operator principal)

## Spec

Let an operator export each month's `tenant_usage` counts for the true-up invoice, and optionally pre-fill the provisioning wizard from a signed-contract webhook, without ever holding price or payment data.

- **files**:
  - apps/api/aip/modules/tenancy/entitlements/export.py
  - apps/api/aip/modules/tenancy/contract_intake.py
  - apps/api/aip/modules/tenancy/routes.py (two operator routes)
  - apps/api/aip/modules/tenancy/tests/test_usage_export.py
  - apps/api/aip/modules/tenancy/tests/test_contract_intake.py
- **steps**:
  - 1. `GET /api/v1/platform/usage-export?month=YYYY-MM&format=csv|json` (operator principal only). One row per tenant: `tenant_slug`, `contract_ref`, `plan_code`, `month`, active users per class, `storage_gb`, `active_projects`, `api_calls`, `jobs`, `ai_spend_aud`, and the plan's limits for the same fields so overage can be invoiced without a lookup. No names, emails or business data.
  - 2. The response carries `X-Content-SHA256` of the body and writes an `platform.usage_exported` audit event (operator id, month, row count).
  - 3. `POST /api/v1/platform/contract-intake` accepts `{contract_ref, tenant_name, plan_code, term, starts_on, renewal_date, seat_limits}` signed with an HMAC secret from settings (never from the repo). It stores a pending intake row an operator can load into the wizard. It never creates a tenant and never changes a subscription.
  - 4. An unsigned, badly signed or replayed request (same `contract_ref` and nonce) returns 401 and stores nothing.
- **acceptance**:
  - Only a platform operator can export; a tenant admin gets 403.
  - The export contains no personal data and a verifiable hash.
  - Contract intake cannot create or change a tenant.
- **tests**:
  - **unit**:
    - HMAC verification accepts a valid signature and rejects a changed body.
  - **integration**:
    - Export 2026-10 with two tenants. Expected: 2 rows, columns exactly as listed, hash matches the body.
    - Tenant admin calls the export. Expected: 403.
    - Valid intake. Expected: 202, one pending row, zero new tenants. Replay. Expected: 401.
