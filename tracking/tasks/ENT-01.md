# ENT-01 — EntitlementService, tenant_subscription, tenant_usage; flags vs entitlements (ADR 0008)
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0008](../../docs/adr/0008-entitlements-and-commercial-model.md), [0001](../../docs/adr/0001-greenfield-python-backend.md) (Python backend, TS frontends), [0002](../../docs/adr/0002-data-access-and-migrations.md) (tenant template, `with_tenant`), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox event), [0004](../../docs/adr/0004-repository-layout.md) (module layout, `apps/web`)
4. Only if the step needs it: [`docs/reviews/03-saas.md`](../../docs/reviews/03-saas.md) ("Billing and plans", "Entitlements", "Seat definition and metering")

## Spec

Provide a single `EntitlementService.check(tenant, feature | limit)` that resolves plan → add-on → tenant override → site/project toggle, backed by `tenant_subscription` and monthly `tenant_usage` and kept separate from release flags, with a read-only "Plan and usage" page. There is no payment provider and no self-registration.

- **files**:
  - apps/api/migrations/versions/<rev>_tenancy_entitlements.py
  - apps/api/aip/modules/tenancy/tables.py (add the three tables)
  - apps/api/aip/modules/tenancy/entitlements/__init__.py
  - apps/api/aip/modules/tenancy/entitlements/plans.py
  - apps/api/aip/modules/tenancy/entitlements/resolve.py
  - apps/api/aip/modules/tenancy/entitlements/service.py
  - apps/api/aip/modules/tenancy/entitlements/dependencies.py (`requires_entitlement`)
  - apps/api/aip/modules/tenancy/entitlements/usage.py
  - apps/api/aip/modules/tenancy/entitlements/snapshot_cli.py
  - apps/api/aip/modules/tenancy/schemas.py (add request/response models)
  - apps/api/aip/modules/tenancy/routes.py (operator and plan-and-usage routes)
  - apps/api/aip/modules/tenancy/events.py (`tenant.entitlements_changed`)
  - apps/api/aip/modules/tenancy/api.py
  - apps/api/aip/modules/tenancy/seed.py (add a `professional` subscription for `kaefer-demo`, `core` for `tenant-b`)
  - apps/web/src/features/tenancy/PlanAndUsagePage.tsx
  - apps/api/aip/modules/tenancy/tests/entitlements/
- **steps**:
  - 1. Key namespaces: `feature.<name>` (boolean, e.g. `feature.bim`, `feature.portal`) and `limit.<name>` (number: `limit.seats.staff`, `limit.seats.field`, `limit.seats.portal`, `limit.storage_gb`, `limit.api_calls_per_min`, `limit.ai_spend_aud_month`). The service rejects `release.*` keys with `InvalidEntitlementKey`: release flags (rollout, kill switch) belong to ARCH-08 and never read subscription data. A route is reachable only when the entitlement allows it AND its release flag is on.
  - 2. `plans.py` defines plans and add-ons in code as Pydantic v2 models, versioned and validated at import/app startup (a negative limit fails startup): plans `core`, `professional` and `enterprise`, each `{code, version, features, limits}`, and add-ons such as `bim` that switch features on or raise limits. Platform core modules (identity, access, tenancy, projects) are never entitlement-gated.
  - 3. Revision (rendered from `db/templates/tenant_table.sql.tpl`, FORCE RLS). Table `tenant_subscription`: tenant_id PK/FK, plan_code, plan_version, term (`annual`|`multi_year`|`trial`|`sandbox`), starts_on, ends_on, renewal_date, seat_limits jsonb `{staff, field, portal}`, storage_gb, add_ons text[], contract_ref, status (`active`|`expired`|`suspended`), updated_by, timestamps. Table `tenant_entitlement_override`: id, tenant_id, key, value jsonb, reason NOT NULL, expires_at NULL, created_by, created_at, deleted_at. Table `tenant_usage`: tenant_id, period date (first day of the month), active_users jsonb `{staff, field, portal}`, storage_bytes, jobs_count, ai_spend_cents, captured_at, PK (tenant_id, period).
  - 4. `resolve.py` is a pure function `resolve(key, *, subscription, plan, add_ons, overrides, toggles, now) -> Resolution(value, source)` with `source` in `plan|add_on|override|toggle|none`. Order: plan; then add-ons (features OR; a limit takes the larger value); then an unexpired tenant override, which wins even when lower; then a site/project toggle, which can only switch a feature off, never on, and never changes limits. A missing subscription, or one that is `expired` or `suspended`, gives every gated feature false with source `none` (fail closed).
  - 5. `EntitlementService` exported from `api.py`: `check(tenant_id, feature_key, *, project_id=None) -> Decision(allowed, source)`; `check_limit(tenant_id, limit_key, requested_total) -> LimitDecision(allowed, limit, source)`; `list(tenant_id)`; `check_seat(conn, tenant_id, user_class)` for identity to call on activation later. Results are cached in-process per tenant for 60 s (`cachetools.TTLCache`) and invalidated immediately on writes in the same process. Writes insert the outbox event `tenant.entitlements_changed` in the same `with_tenant` transaction; ARCH-08 and other instances subscribe to it. Toggles come from a `ScopeToggleProvider` Protocol (default none; the projects module registers later). Usage comes from a `UsageSource` Protocol registry (identity contributes active users per class, uploads contributes storage). `snapshot_usage(tenant_id, period)` upserts `tenant_usage`; the CLI `uv run python -m aip.modules.tenancy.entitlements.snapshot_cli --period 2026-10` runs it until OPS schedules it as a Procrastinate periodic job. The service takes a `Clock` (callable returning `datetime`) so tests can advance time.
  - 6. FastAPI dependency `requires_entitlement("feature.bim")` (used as `dependencies=[Depends(requires_entitlement("feature.bim"))]`) returns 403 `{"code": "NOT_ENTITLED", "key": "feature.bim"}`.
  - 7. Operator API (platform-operator principal only; `reason` required): `PUT /api/v1/platform/tenants/{tenant_id}/subscription`, plus `POST` and `DELETE /api/v1/platform/tenants/{tenant_id}/entitlement-overrides`. Tenant API: `GET /api/v1/settings/plan-and-usage` (permission `tenancy.plan.read`) returns `{plan, term, renewal_date, features:[{key, enabled, source}], limits:[{key, limit, used}]}` (Pydantic response model; TS types come from the generated `packages/api-client`).
  - 8. `/settings/billing` (TanStack Router route in `apps/web`) renders `PlanAndUsagePage` read-only using the generated client: plan, term, renewal date, seats used against the limit per class, and storage, with terminology keys for every label. There is no "Change plan", no invoices and no payment provider. `/register` and any self-signup API stay absent (sales-led, operator-provisioned).
- **acceptance**:
  - Every entitlement decision goes through `EntitlementService` and reports its source.
  - A project toggle can narrow but never grant. Expired overrides are ignored. A tenant without an active subscription gets no gated features.
  - Release flags and entitlements use separate keys and stores.
  - Tenant admins can read their plan and usage but cannot change them; only operators can.
- **tests**:
  - **unit** (pytest):
    - Plan `core` (`feature.bim=false`) with add-on `bim`: `feature.bim` resolves to true with source `add_on`.
    - An override `feature.bim=false` on top of the add-on resolves to false with source `override`.
    - An override that expired yesterday is ignored.
    - A project toggle off resolves to false with source `toggle`. A project toggle on while the plan is false still resolves to false.
    - `limit.seats.staff` with plan 50 and override 80 resolves to 80 with source `override`.
    - No subscription: `feature.bim` resolves to false with source `none`.
    - `check(t, "release.new_nav")` raises `InvalidEntitlementKey`.
    - A plan with a negative limit raises `pydantic.ValidationError` when the plan registry loads.
  - **integration** (pytest + testcontainers-python, httpx `AsyncClient`):
    - As `aip_app` inside `with_tenant(A)`, `SELECT * FROM tenant_subscription` returns exactly 1 row (A's).
    - A fixture route with `requires_entitlement("feature.bim")` for a tenant without it. Expected: 403 `NOT_ENTITLED`. The operator adds an override. Expected: the next call returns 200. Advance the fake clock past `expires_at`. Expected: 403 again, and a `tenant.entitlements_changed` row exists in `domain_events` for the override write.
    - `check_limit(t, "limit.seats.staff", 51)` with a limit of 50 returns `allowed=False, limit=50`.
    - `snapshot_usage` with a fake `UsageSource` `{staff: 12, field: 40, portal: 3}` for 2026-10, run twice. Expected: 1 `tenant_usage` row with those values.
    - A tenant admin calls `PUT .../subscription`. Expected: 403. A platform operator. Expected: 200.
    - `POST /api/v1/auth/register` returns 404.
  - **e2e**:
    - Playwright: the `kaefer-demo` tenant admin opens `/settings/billing`. Expected: "Plan and usage" shows plan `professional`, the renewal date and seats used against the limit per class, and there is no "Change plan" or payment control.

## Added by ADR 0017 (2026-10-10)

- `contract_ref` is validated: required when `term` is `annual` or `multi_year`, optional for `trial` and `sandbox`.
  `PUT .../subscription` rejects a production term without it (422 `CONTRACT_REF_REQUIRED`) and records the old and new
  value in the audit event. The product stores no price, invoice or payment data.
- The plan-and-usage page shows `contract_ref` and `renewal_date` read-only. No invoice list, plan change or payment
  control (see `docs/blueprint/pages-global.md`, "Plan and usage").
- Tests: unit (`annual` without `contract_ref` is invalid; `sandbox` without is valid); integration (tenant admin
  `PUT` is 403; operator `PUT` without `contract_ref` on `annual` is 422; with it is 200 and audited).
- The monthly usage export is ENT-02, not this task.

## Added by the owner's plan structure (2026-10-10, ADR 0008)

- `plans.py` defines `core`, `professional` and `enterprise` with the limits and features in the ADR 0008 table. New limit keys: `limit.seats.full` (staff plus field seats together), `limit.seats.portal` (reviewer seats), `limit.projects`, `limit.api_calls_per_day`; keep `limit.storage_gb` and `limit.ai_spend_aud_month`. New feature keys: `feature.api`, `feature.sso`, `feature.custom_categories`, `feature.reporting_feed`.
- Prices never appear in code or the database. No row-count limits (ADR 0008 adjustment A).
- Tests: `core` with 1 full user: `check_limit("limit.seats.full", 2)` is not allowed; `professional` allows 5 and refuses 6; `limit.projects` 2 for `core`; `feature.sso` false for `professional` and true for `enterprise`; a negative limit still fails plan load.

## Added by owner adjustments A to C (2026-10-10, ADR 0008)

- New limit key `limit.db_gb` (included database size per plan) and add-ons `add_on.db_block_20gb` (+20 GB) and `add_on.reporting_feed`. Plan amounts are in ADR 0008 (core's included size is open, OPEN-QUESTIONS 24); prices stay out of the repository.
- `tenant_usage.db_bytes_est`: a nightly job estimates each tenant's database size by summing the byte size of its rows over every tenant table (including the audit log), using the tenant's `tenant_id` filter, and records the method version with the figure. `check_limit("limit.db_gb", …)` uses it. The plan-and-usage page shows the estimate and states how it is measured.
- Tests: two tenants with known row counts produce estimates in the expected ratio; a tenant over its included size with no add-on is reported over limit but not blocked from sign-off or reads (limits warn, they never lock evidence away).
