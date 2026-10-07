# SaaS platform specialist review

## Verdict
**The platform thinking is strong, but the commercial plan is weak and the scope is far too big.** Tenant isolation and configuration-over-code are designed better than in most mid-market SaaS blueprints. But the blueprint treats AIP as a platform programme, not a product with a first paying customer. There are 64 modules, every scout suggestion is "accepted", and P0 alone covers 15 modules with SOC 2-grade controls. A TypeScript rebuild also discards 48 shipped phases (`02-advisor-summaries.md`, delivery planner). Meanwhile Kaefer gets nothing new until P1 parity is done. The tech advisor estimated that at 6-12 months, and `assets/README.md` notes "solo capacity". Billing, plans and entitlements are not designed: there is one settings page and no model behind it. **Verdict: approve the tenancy and config foundations, cut P0 by about 40%, add a thin commercial layer (plans, entitlements, metering), and redefine P1 as "Kaefer live on the new platform", with config tooling shipped as operator tools first.**

## Strengths
- **Pooled tenancy done properly.** FORCE RLS, a non-owner role, `SET LOCAL app.tenant_id` that fails closed, tenant-scoped Redis/S3/queue key builders (TENANCY-02), and isolation tests generated from the catalogue (DATABASE-07, TESTING-02/03). The schema is the same for pooled and silo, and silos are an IaC variable (`tenancy/README.md`). That is the right path from pool to silo.
- **Config over code is designed in from the start.** Terms are keys with a layered chain: platform, market pack, tenant, client, project. Workflow codes are neutral and statuses are mapped. Item types are versioned with pinning. Form revisions are frozen. Workflow definitions pin in-flight instances. JSONLogic is the single expression language. This is what lets one codebase serve Kaefer/Rio and then other markets.
- **The tenant configuration bundle** (export, diff, import of templates, types, workflows, terms and rules; `arch/README.md`) is the right primitive for onboarding and sandbox-to-prod promotion.
- **Lifecycle basics are there:** a provisioning wizard (TENANCY-05, transactional and idempotent), offboarding with a deletion certificate, customer-approved support access (TENANCY-06), and tenant export with dual approval (`data_io`).
- **Noisy-neighbour guard exists.** Redis API counters with 429 and Retry-After, storage and job checks on enqueue, and 80%/100% alerts (TENANCY-06).
- **The asset-centric wedge is clearly set apart** from project-centric rivals (Procore, ACC, Aconex). Reporting already states: "anything not demonstrable in the pilot is not MVP". Apply that rule everywhere.

## Top risks
| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **Time-to-value gap from the rebuild.** Kaefer sees nothing new until P0 (15 modules) and P1 (16 modules) are done, which is likely 9-15 months for a solo or small team. AIP is live, so the customer may churn or lose patience. | Critical | Keep FastAPI AIP serving Kaefer (bug fixes only). Ship the new platform as a strangler, with Kaefer live by month 4-6 on a cut P1 (see MVP). Set a hard date in an ADR. |
| 2 | **Scope inflation.** 64 modules, every scout item "accepted". P0 includes breach register, control catalogue, quarterly access review, IP allow-list, crypto-shred, glossary, alias mapping and unit conversion before any inspection exists. | Critical | Add an MVP-cut ADR. Move compliance-programme tooling to Vanta/Drata. Defer about 25 of the 59 P0 tasks (list below). |
| 3 | **Blueprint and tasks out of sync.** `01-decisions.md` says "Keep Alembic raw SQL" and "Redis queue (arq or Celery)". OPS-02 says "arq runner" with `.py` paths. 32 of 59 tasks still reference Python, Alembic or `backend/app` paths. There is no `docs/adr/` folder at all, though decisions defer to it. | High | Write ADR-000 "TS stack reconciliation" (BullMQ, Drizzle or Kysely plus SQL migrations, NestJS paths). Regenerate the affected tasks before anyone builds. |
| 4 | **Billing, plans and entitlements are missing.** `/settings/billing` shows plan, seats, invoices and "Change plan", but there is no plan, seat, subscription or invoice model. ARCH-08 `tenant_feature_flags` and TENANCY-05 `tenant_modules` overlap and neither is tied to a plan. | High | Use a single entitlements service (plan to features and limits, plus per-tenant overrides). Meter seats and storage from day 1. Invoice manually or via Stripe later (see Gaps). |
| 5 | **Config sprawl without a tenant-upgrade story.** Item types, forms, rules, workflows, term packs, ref packs, starter packs and project templates each have their own versioning. Nothing says how a *platform* update to a starter pack or default terms reaches tenants that customised it. | High | Use one "content pack" model: a global version plus a tenant fork with a 3-way diff on upgrade. Reuse the config bundle diff. Pin per tenant. Never auto-apply. |
| 6 | **Pooled RLS for Rio Tinto and mining procurement.** Security flags it as the top risk. Silo criteria are an open question, and the shared key versus per-tenant KMS conflict is unresolved (`tenancy/README.md`). | High | Decide now: per-tenant KMS data keys (envelope) are cheap and resolve crypto-shred. Publish silo criteria and price silo as an Enterprise tier. |
| 7 | **No-code designers are a big build for one customer.** Form designer, rule editor with impact preview, workflow designer with dry-run, and schema migration preview are each L-sized. | High | For Kaefer, have the operator author config as JSON/bundles with lint and test. Ship the self-serve designers when customer #2 or #3 pays. |
| 8 | **Noisy neighbour is only rate-limited at the API.** PDF/Gotenberg, imports, exports and sync bursts share workers. One queue per tenant (`aip:{tenant}:jobs`) with BullMQ means N queues to poll and no fair scheduling. | Medium | Use shared queues per job class with BullMQ group/rate limiting per tenant (or a weighted fair dispatcher). Set per-tenant concurrency caps on Gotenberg. Add `statement_timeout` per role. |
| 9 | **P0 module tasks are missing.** identity, access, approvals, uploads, audit, design and projects are P0 but have no tasks. The 59 tasks cover only 8 modules. | Medium | Write tasks for these before starting, or move them per the MVP cut. |
| 10 | **Compliance cost and timing.** SOC 2 Type I evidence in P2, IRAP and ISO "programme" modules built in-app. | Medium | Buy Vanta/Drata. Keep only the in-app controls auditors test (isolation, audit chain, access review export). |

## Gaps
- **Billing and plans.** Nothing defines plans, seat types (full vs field/PIN vs portal), metering, invoicing, trials or dunning, yet the nav exposes it. Mid-market construction is usually annual-contract, invoice-billed and priced by project or seat band. Recommendation: no Stripe at launch. Add a `tenant_subscription` table (plan_code, term, seat_limits by user class, storage_gb, add-ons, contract_ref, renewal_date) plus monthly usage snapshots. Hide `/settings/billing` until it exists, or show "Plan and usage" read-only.
- **Entitlements.** Merge `tenant_modules`, `tenant_feature_flags`, quota defaults and AI budget caps (`ai_gov`) into one `EntitlementService.check(tenant, feature|limit)`. Resolution order: plan, then add-on, then tenant override, then site/project toggle (`05-access-matrix` already wants per-site flags). Release flags (rollout or kill switch) must be kept separate from entitlements (what was paid for). Right now they are conflated.
- **Seat definition and metering.** 500-5,000 users, mostly field users and external portal reviewers, so pricing depends on user classes. Count active users per class per month in `tenant_usage`. Without this the business cannot price or spot heavy tenants (`ops/features-market.md` says as much).
- **Onboarding and time-to-first-value.** The provisioning wizard exists, but there is no onboarding journey: no data migration playbook, no checklist (import tree, load templates, invite users, first inspection), and no sandbox tenant. The config bundle could provide a "Kaefer reference config" to clone for the next contractor. Add a tenant `environment` (sandbox or production) with bundle promotion between them.
- **Self-serve vs sales-led.** Not stated. For this segment and IRAP/Rio posture: sales-led, operator-provisioned, no self-signup. Write that down so nobody builds signup or trial flows.
- **Tenant config upgrade path.** Covered in risk 5. Also needed: a "platform default changed" changelog per tenant, and a compatibility check when a platform release changes a field type or evaluator version. `form_revisions.evaluator_version` is a good start.
- **Platform operator console.** Only `/platform/tenants` exists. Also needed: per-tenant health, usage, plan, flags, impersonation via a support grant, and job backlog by tenant.
- **Per-tenant SLOs and observability.** Metrics are not labelled by tenant, there are no per-tenant DB statement stats, and no status page or SLA definitions for contracts.
- **Tenant lifecycle states.** Statuses exist, but no rules say what "suspended" (non-payment) blocks: read-only versus locked, and whether export stays available.
- **Hierarchical / multi-entity tenants.** Kaefer has regional entities (Kaefer WA and others). Decide whether these are one tenant with organisations or several tenants, and whether parent-tenant config inheritance is needed. This affects billing and bundles.

## MVP cut recommendation
**Release 1, "Kaefer live" (target 4-6 months): one tenant in production, a second demo tenant proving isolation and renaming.**

| In R1 | Cut to R1 scope |
|---|---|
| Tenancy | Pooled RLS, key builders, isolation CI, operator-run provisioning script/wizard, `tenant_subscription` and entitlements service (flags and modules merged), API quotas |
| Identity/access | Keycloak SSO and MFA, email+password, project-scoped roles, the matrix-generated permission tests. Magic link/PIN only if field crews need it on day 1 |
| Terms | Key dictionary, tenant and project override levels, en-AU pack, lint rule. Defer glossary, aliases, pack diff/rollback UI and unit conversion beyond storing SI |
| Workflow | Engine plus the inspection review and hold-point presets, versioned. Defer route designer, dry-run UI, authority matrix and delegation UI |
| Assets/item types | ltree tree, item types with versioned JSON schema, CSV tree import with dry-run, register pages. Defer inheritance, calculated attributes and RBI |
| Forms/inspections | Renderer, frozen revisions, ITP and hold points, cert/calibration hard-block, RSW completion gate. Templates authored by the operator as JSON and bundles. Defer the full drag-drop designer |
| Outputs | Gotenberg PDF of inspection/ITP reports (pulled forward from P2: Kaefer needs it to hand over to Rio) |
| Issues | NCR basic lifecycle on the workflow engine |
| Audit/uploads | Hash-chained audit, quarantine-scan upload path |
| Data | AIP to new platform migration and reconciliation, register/CSV export, tenant export (operator-run) |
| Ops | Terraform on ECS Sydney, build-promote, backups with a restore test, per-tenant metrics labels |

**Deferred (in order of commercial pull):**
- **R2, sell to customer #2:** self-serve form designer, config bundle export/import UI, offline PWA, read-only portal with witness, comments/tasks, documents.
- **R3:** rules authoring UI, diary/signing, punch list, search, dashboards, equipment/inventory, components traceability depth.
- **Later:** everything in P3/P4. Specifically drop or park until paid for: procurement, change, logistics, temporary works, interfaces, meetings, voice, prefab, service, commissioning, ref_packs cost data, AI assistant, SAP/Maximo connectors, siloed stack, eu-west-2 and ap-southeast-1.
- **From the 59 P0 tasks, defer:** SECURITY-03/04/05 (use Vanta), SECURITY-07, TENANCY-04 (asset sharing until the portal exists), TENANCY-07 (crypto-shred; keep a manual runbook), TERMS-03/04/06, OPS-06, TESTING-07 (no offline yet), ARCH-06 replay/catalogue UI (keep the outbox and dispatcher).

**Packaging hypothesis to validate with Kaefer:**
- **Core** (assets, inspections/ITP, NCR, PDF): per active full user, with field users in bands.
- **Pro** (+ portal, offline, documents, signing).
- **Enterprise** (+ SSO/SCIM, silo option, custom retention, API).
- AI is a metered add-on.
- Gate SSO and SCIM by tier, since they carry a per-connection cost.

## Recommended decisions / ADRs
1. **ADR-000 TS stack reconciliation.** Use BullMQ (not arq or Celery), a TS migration tool with raw SQL files, and NestJS paths. Supersede the Python lines in `01-decisions.md`. Regenerate the 32 tasks that still carry Python, Alembic or `backend/app` paths.
2. **ADR-001 Strangler and R1 date.** AIP FastAPI stays in production for Kaefer until R1 cutover, then is frozen. Migration and reconciliation is an R1 exit gate.
3. **ADR-002 Plans, entitlements and metering.** One EntitlementService, release flags kept apart from entitlements, `tenant_subscription` plus `tenant_usage`. Invoicing is manual at launch.
4. **ADR-003 Content-pack versioning and tenant upgrade.** Global pack, then tenant fork, 3-way diff, opt-in upgrade. Applies to terms, starter packs, form seeds, workflow presets and rule packs.
5. **ADR-004 Key scheme.** Per-tenant KMS data keys (envelope) replace "shared key with tenant prefixes". Crypto-shred respects legal hold.
6. **ADR-005 Silo criteria and pricing.** Who must use a silo (IRAP or client mandate), when it gets built (on signed contract), and that it is priced as Enterprise plus a setup fee.
7. **ADR-006 Fair job scheduling.** Shared queues per job class with per-tenant concurrency and rate limits. Gotenberg and import workers run in separate pools.
8. **ADR-007 Sales-led onboarding.** No self-signup. Operator provisioning, plus a sandbox tenant per customer with bundle promotion.
9. **ADR-008 Scope governance.** "Accepted" suggestions go to a backlog, not to scope. A module enters a phase only with a named paying customer or a pilot-demonstrable need.

## Questions for the owner
1. Is Kaefer paying now, on what terms (per seat, per project, enterprise licence), and what does the contract say about renewal and feature delivery dates?
2. What is the hard date by which Kaefer must be on the new platform, and will AIP FastAPI keep running for them until then?
3. Team size: solo, or hires planned? The 64-module plan needs a realistic burn-down.
4. Which user classes count as billable seats: field PIN users, Rio Tinto portal reviewers, subcontractors?
5. Who is customer #2 (another contractor in mining, or a different vertical)? That decides whether R2 is the self-serve form designer or the portal and offline.
6. Does Rio Tinto (or Kaefer's IT) require a siloed or dedicated deployment or per-tenant keys contractually? That changes whether "pooled only" holds at launch.
7. Is Kaefer one tenant with regional organisations, or several tenants under a parent account?
8. Should `/settings/billing` exist at launch, or is billing contract-only via invoice?
9. Who authors tenant configuration at launch: you as operator, or Kaefer admins? This decides whether no-code designers are R1 or R2.
10. Will you buy Vanta/Drata rather than build the in-app control catalogue, breach register and access-review tooling?

Key files: `/home/user/Project-AIP/docs/blueprint/01-decisions.md`, `/home/user/Project-AIP/docs/blueprint/06-build-order.md`, `/home/user/Project-AIP/docs/blueprint/modules/tenancy/README.md`, `/home/user/Project-AIP/docs/blueprint/modules/arch/README.md`, `/home/user/Project-AIP/docs/blueprint/pages-global.md` (line 479, Billing page), `/home/user/Project-AIP/tracking/tasks/OPS-02.md` (arq), `/home/user/Project-AIP/tracking/tasks/ARCH-08.md` and `/home/user/Project-AIP/tracking/tasks/TENANCY-05.md` (overlapping flags/modules), `/home/user/Project-AIP/tracking/tasks/TENANCY-06.md` (quotas).
