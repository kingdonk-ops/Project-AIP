# ADR 0008: One entitlement service; sales-led onboarding; contract billing at launch

- **Status:** accepted (owner, 2026-10-10: the plan structure below); adjustments A to D accepted by the owner (A to C on 2026-10-10, D on 2026-10-11)
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

## Plans and limits (owner, 2026-10-10)

Prices are set in the company systems and are deliberately not recorded in this public repository. Plan codes stay
`core`, `professional` and `enterprise`; the display names (Essentials, Professional, Enterprise) come from terminology.
Kaefer is **one tenant**; its regions are organisations with projects beneath them (TENANCY-03), not separate tenants.

| Dimension | `core` (Essentials) | `professional` | `enterprise` |
|---|---|---|---|
| Included full users (staff and field seats) | 1 | 5 | custom, volume scale |
| Reviewer seats (portal class: read-only plus sign-off) | 3 | 20 | unlimited |
| Extra seats | billed per seat | billed per seat | volume scale; reviewer seats included |
| Active projects | 2 | 15 | unlimited |
| Included file storage | 25 GB pooled | 250 GB pooled | 2 TB or more |
| Included database size | 5 GB | 20 GB | 100 GB |
| Inspection categories | standard set | unlimited custom, form builder | full taxonomies, code matching |
| Integration API | none | standard REST, 5,000 requests per day | dedicated, webhooks |
| Reporting | CSV and Excel export | in-app dashboards and a read-only reporting feed | dedicated capacity option |
| Sign-in | email, password, 2FA | email, password, app MFA | adds SAML or OIDC single sign-on |
| Deployment | pooled | pooled | pooled by default; siloed is an option built when a contract requires it |
| Support | knowledge base, email | business-hours email | uptime commitment, named contact |

Overage (extra seats, storage, projects) is invoiced from the monthly usage export (ENT-02), never charged in the app.
Every tenant has its own KMS key regardless of plan (ADR 0006), and the same immutable audit log (see B).
`limit.seats.full` (staff plus field), `limit.seats.portal`, `limit.projects`, `limit.storage_gb` and
`limit.api_calls_per_day` and `limit.db_gb` are the keys ENT-01 defines. Add-ons: `add_on.db_block_20gb` (another 20 GB of
database, price in the company systems) and `add_on.reporting_feed` (see C).

### Adjustments (A to C accepted by the owner on 2026-10-10, D on 2026-10-11)

- **A. No database-row caps; meter size in GB.** Rows cannot be counted consistently across tables. Meter seats,
  active projects, file storage and **database size in GB** (an included amount per plan, then extra blocks of 20 GB).
  The cluster is shared, so no per-tenant database file exists: a nightly job estimates each tenant's size by summing
  the byte size of its rows in every tenant table (including the audit log), and the page shows the estimate and how
  it is measured.
- **B. One audit log for every plan (accepted: the 30-day audit tier is dropped).** The append-only hash-chained audit log is built once (P0). Plans may differ in
  how long the searchable view and export are offered, but never in whether sign-off evidence is kept.
- **C. Power BI (accepted).** Only the customer-owned mode: a read-only, tenant-scoped reporting feed that a customer's own
  Power BI reads with their own licences, sold as the `reporting_feed` add-on (the price is set in the company systems,
  not in this repository). It needs its own security review before it is built, because it gives a customer's tool
  direct read access (per-tenant credentials, row-level security, rate limits, audit of every read). Embedded and dedicated Power BI capacity need paid Azure capacity, add Microsoft as a sub-processor
  and raise residency questions, which conflicts with the no-paid-licence rule. They wait for an owner decision and
  their own ADR. In-app dashboards use open-source charts.
- **D. No on-premises deployment.** "Dedicated" means a siloed deployment in our cloud account, after R1, on contract.

## Contract link (added 2026-10-10, ADR 0017)

`tenant_subscription.contract_ref` is the only join to the company's contract system (opaque id, no prices).
Required for `annual` and `multi_year` terms. Prices, invoices and payments stay outside the product. Monthly
`tenant_usage` counts are exported by an operator for the true-up invoice (ENT-02).

## Consequences

ARCH-08 and TENANCY-05 build their flags and module toggles on this service (task ENT-01).

## Archive plan (backlog, ADR 0022)

Plan code `archive`: for customers who must keep records after leaving. Their data becomes a sealed bundle held with the reports
and files in cold storage and is read through a separate archive area with one or two auditor seats (search and export only).
The tenant's rows leave the shared database, so the plan carries no database-size charge. Not part of R1. The price is set in
the company systems.
