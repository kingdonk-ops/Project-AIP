# ENT-01 — EntitlementService, tenant_subscription, tenant_usage; flags vs entitlements (ADR 0008)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`tenancy`](../../docs/blueprint/modules/tenancy/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DATABASE-02, TENANCY-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/tenancy/README.md`](../../docs/blueprint/modules/tenancy/README.md)
3. ADRs: [0008](../../docs/adr/0008-entitlements-and-commercial-model.md), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. Only if the step needs it: [`docs/reviews/03-saas.md`](../../docs/reviews/03-saas.md) ("Billing and plans", "Entitlements", "Seat definition and metering")

## Spec

Provide a single `EntitlementService.check(tenant, feature | limit)` that resolves plan → add-on → tenant override → site/project toggle, backed by `tenant_subscription` and monthly `tenant_usage` and kept separate from release flags, with a read-only "Plan and usage" page. There is no payment provider and no self-registration.

- **files**:
  - db/migrations/<timestamp>_tenancy_entitlements.sql
  - apps/api/src/modules/tenancy/entitlements/plans.ts
  - apps/api/src/modules/tenancy/entitlements/resolve.ts
  - apps/api/src/modules/tenancy/entitlements/entitlement.service.ts
  - apps/api/src/modules/tenancy/entitlements/requires-entitlement.guard.ts
  - apps/api/src/modules/tenancy/entitlements/usage.service.ts
  - apps/api/src/modules/tenancy/entitlements/subscription.controller.ts
  - apps/api/src/modules/tenancy/entitlements/plan-usage.controller.ts
  - apps/api/src/modules/tenancy/api.ts
  - apps/web/src/features/tenancy/PlanAndUsagePage.tsx
  - apps/api/src/modules/tenancy/tests/entitlements/
- **steps**:
  - 1. Key namespaces: `feature.<name>` (boolean, e.g. `feature.bim`, `feature.portal`) and `limit.<name>` (number: `limit.seats.staff`, `limit.seats.field`, `limit.seats.portal`, `limit.storage_gb`, `limit.api_calls_per_min`, `limit.ai_spend_aud_month`). The service rejects `release.*` keys with `InvalidEntitlementKey`: release flags (rollout, kill switch) belong to ARCH-08 and never read subscription data. A route is reachable only when the entitlement allows it AND its release flag is on.
  - 2. `plans.ts` defines plans and add-ons in code, versioned and Zod-validated at boot: plans `core`, `professional` and `enterprise`, each `{code, version, features, limits}`, and add-ons such as `bim` that switch features on or raise limits. Platform core modules (identity, access, tenancy, projects) are never entitlement-gated.
  - 3. Migration (tenant template, FORCE RLS). Table `tenant_subscription`: tenant_id PK/FK, plan_code, plan_version, term (`annual`|`multi_year`|`trial`|`sandbox`), starts_on, ends_on, renewal_date, seat_limits jsonb `{staff, field, portal}`, storage_gb, add_ons text[], contract_ref, status (`active`|`expired`|`suspended`), updated_by, timestamps. Table `tenant_entitlement_override`: id, tenant_id, key, value jsonb, reason NOT NULL, expires_at NULL, created_by, created_at, deleted_at. Table `tenant_usage`: tenant_id, period date (first day of the month), active_users jsonb `{staff, field, portal}`, storage_bytes, jobs_count, ai_spend_cents, captured_at, PK (tenant_id, period).
  - 4. `resolve.ts` is a pure function `resolve(key, {subscription, plan, addOns, overrides, toggles, now})` returning `{value, source:'plan'|'add_on'|'override'|'toggle'|'none'}`. Order: plan; then add-ons (features OR; a limit takes the larger value); then an unexpired tenant override, which wins even when lower; then a site/project toggle, which can only switch a feature off, never on, and never changes limits. A missing subscription, or one that is `expired` or `suspended`, gives every gated feature false with source `none` (fail closed).
  - 5. `EntitlementService` exported from `api.ts`: `check(tenantId, featureKey, {projectId?})` returns `{allowed, source}`; `checkLimit(tenantId, limitKey, requestedTotal)` returns `{allowed, limit, source}`; `list(tenantId)`; `checkSeat(tx, tenantId, userClass)` for identity to call on activation later. Results are cached in-process per tenant for 60 s and invalidated immediately on writes in the same process. Writes emit the outbox event `tenant.entitlements_changed`, which ARCH-08 and other instances subscribe to. Toggles come from a `ScopeToggleProvider` port (default none; the projects module registers later). Usage comes from a `UsageSource` port registry (identity contributes active users per class, uploads contributes storage). `snapshotUsage(tenantId, period)` upserts `tenant_usage`, and the CLI `pnpm tenancy:usage-snapshot --period 2026-10` runs it until OPS schedules the job.
  - 6. `@RequiresEntitlement('feature.bim')` decorator and guard return 403 `{code:'NOT_ENTITLED', key}`.
  - 7. Operator API (platform-operator principal only; `reason` required): `PUT /api/v1/platform/tenants/:tenantId/subscription`, plus `POST` and `DELETE /api/v1/platform/tenants/:tenantId/entitlement-overrides`. Tenant API: `GET /api/v1/settings/plan-and-usage` (`tenancy.plan.read`) returns `{plan, term, renewalDate, features:[{key, enabled, source}], limits:[{key, limit, used}]}`.
  - 8. `/settings/billing` renders `PlanAndUsagePage` read-only: plan, term, renewal date, seats used against the limit per class, and storage. There is no "Change plan", no invoices and no payment provider. `/register` and any self-signup API stay absent (sales-led, operator-provisioned).
- **acceptance**:
  - Every entitlement decision goes through `EntitlementService` and reports its source.
  - A project toggle can narrow but never grant. Expired overrides are ignored. A tenant without an active subscription gets no gated features.
  - Release flags and entitlements use separate keys and stores.
  - Tenant admins can read their plan and usage but cannot change them; only operators can.
- **tests**:
  - **unit**:
    - Plan `core` (`feature.bim=false`) with add-on `bim`: `feature.bim` resolves to true with source `add_on`.
    - An override `feature.bim=false` on top of the add-on resolves to false with source `override`.
    - An override that expired yesterday is ignored.
    - A project toggle off resolves to false with source `toggle`. A project toggle on while the plan is false still resolves to false.
    - `limit.seats.staff` with plan 50 and override 80 resolves to 80 with source `override`.
    - No subscription: `feature.bim` resolves to false with source `none`.
    - `check(t, 'release.new_nav')` throws `InvalidEntitlementKey`.
    - A plan with a negative limit fails Zod validation at boot.
  - **integration**:
    - Testcontainers: as `aip_app` with tenant A set, `SELECT * FROM tenant_subscription` returns exactly 1 row (A's).
    - A fixture route with `@RequiresEntitlement('feature.bim')` for a tenant without it. Expected: 403 `NOT_ENTITLED`. The operator adds an override. Expected: the next call returns 200. Advance the fake clock past `expires_at`. Expected: 403 again, and a `tenant.entitlements_changed` outbox row exists for the override write.
    - `checkLimit(t, 'limit.seats.staff', 51)` with a limit of 50 returns `allowed: false, limit: 50`.
    - `snapshotUsage` with a fake UsageSource `{staff:12, field:40, portal:3}` for 2026-10, run twice. Expected: 1 `tenant_usage` row with those values.
    - A tenant admin calls `PUT .../subscription`. Expected: 403. A platform operator. Expected: 200.
    - `POST /api/v1/auth/register` returns 404.
  - **e2e**:
    - Playwright: the kaefer tenant admin opens `/settings/billing`. Expected: "Plan and usage" shows plan `professional`, the renewal date and seats used against the limit per class, and there is no "Change plan" or payment control.
