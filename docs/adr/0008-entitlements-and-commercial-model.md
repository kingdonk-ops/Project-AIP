# ADR 0008: One entitlement service; sales-led onboarding; contract billing at launch

- **Status:** proposed: **owner to confirm**
- **Date:** 2026-10-07
- **Affects:** tenancy, arch; ARCH-08, TENANCY-05, TENANCY-06, ai_gov budgets

## Context

The nav has `/settings/billing`, but no plan, seat or subscription model exists. ARCH-08 feature flags and
TENANCY-05 tenant modules overlap, and neither is tied to what a tenant paid for (docs/reviews/03-saas.md).

## Decision

- A single `EntitlementService.check(tenant, feature | limit)`, resolved as plan → add-on → tenant
  override → site/project toggle. **Release flags** (rollout, kill switch) stay separate from **entitlements**.
- Tables: `tenant_subscription` (plan_code, term, seat limits per user class, storage_gb, add-ons,
  contract_ref, renewal_date) and monthly `tenant_usage` (active users per class, storage, jobs, AI spend).
- **Sales-led, operator-provisioned.** `/register` stays off. Each customer gets a sandbox tenant, with
  config-bundle promotion to production.
- No payment provider at launch. `/settings/billing` shows read-only "Plan and usage".

## Consequences

ARCH-08 and TENANCY-05 build their flags and module toggles on this service (task ENT-01).
