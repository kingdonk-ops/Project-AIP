# Testing & quality engineering (`testing`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The test and quality strategy that proves every module works before it ships (Foundations & architecture, suggested phase P0). It applies to the existing AIP platform (Python FastAPI, async SQLAlchemy, Postgres/PostGIS with ltree and JSONB, React/Vite/TypeScript, shadcn/ui, deployed on Coolify) and to every module added later.

What it does
Sets the test approach all modules follow: unit and integration tests run against a real Postgres (no mocked database), mandatory scenario coverage of the highest-risk controls, contract tests for the Python sidecar, and Playwright journeys for the critical flows. CI gates built on these tests block promotion to production. New modules are covered automatically through generated tests, needing only a scenario data file and registration.

Features
- About 80% line coverage on domain and policy code. No blanket coverage number is chased on UI.
- 100% scenario coverage on tenant isolation, the authorisation matrix, workflow transitions, the eligibility gate and audit hash-chain verification.
- Testcontainers Postgres/PostGIS for integration tests.
- Cross-tenant test suite in CI that fails if any new table lacks a tenant_id and a row-level security policy. Tests run the app as a non-owner role without BYPASSRLS, with the tenant set through a per-request, transaction-scoped setting.
- Tenant scoping tests also cover Redis keys, queues, S3 prefixes, search indexes and vector embeddings, since background workers and caches are the usual leak path.
- Permission-matrix test generated from the permissions catalogue, asserting allow and deny per role, project and asset subtree (proves deny-by-default and catches regressions as roles evolve) (accepted).
- IDOR test generated for every ID-addressed endpoint, from the OpenAPI route list.
- Migration tests: up-down-up on every PR, plus a run against a production-size snapshot before release.
- Contract tests between the API and the Python sidecar.
- Playwright journeys (10-15): raise an ITP, sign a hold point, field PIN login, offline capture and sync, approve an inspection.
- Offline sync property tests (Hypothesis): random interleavings of edits, retries and conflicts must converge (accepted).
- Hold-point and completion-gate scenario suite using realistic CUI remediation data; the scenarios double as customer acceptance tests (accepted).
- Golden-file tests for rendered inspection reports and certificates, to detect layout or data drift in published records (accepted).
- Load test (k6) of 5,000 users with a morning-sync burst and a large report-pack run, to validate pooled-stack sizing and queue limits before a large customer onboards (accepted).
- Frontend smoke suite on real mid-range Android and iPad browsers for the field journeys (accepted).
- Fuzz and malicious-file fixtures for uploads; prompt-injection fixtures for AI features.
- Frontend unit tests: Vitest + Testing Library once screens stabilise, with getByLabel accessibility checks.
- Seed script producing realistic, re-runnable demo data.
- Configurable: coverage threshold, required gate list for promotion, journey list and target devices, load profile, fixture refresh schedule, flaky test quarantine policy.
- Notifications: CI gate failed on main, cross-tenant test failure (critical), golden file drift, load test summary, weekly coverage summary.

Interactions
- Operations, hosting and deployment: CI gates block promotion.
- Security and compliance programme: test runs provide evidence of control testing; the production build strip test and permission-matrix test are shared.
- Tenancy, organisations and data residency: cross-tenant test suite.
- Workflow and approvals engine: workflow transition tests.
- Permissions catalogue: source for the generated permission-matrix test.
- AI governance: prompt-injection fixtures feed the red-team suite.

Data
- Realistic seeded demo data and CUI remediation scenario data, re-runnable, kept in repo fixtures using existing tables.
- Production-size snapshot used for pre-release migration tests.
- Golden files for reports and certificates.
- Malicious-file and prompt-injection fixture sets.
- Optional test_evidence_run table (append-only, UPDATE/DELETE revoked, tenant_id and RLS): commit, suite, result, counts, artefact URI and SHA-256. Only built if retaining test evidence is decided.

Pages
- No end-user pages. Outputs are CI results and test reports.
- If exposed to engineers and compliance roles: Test run results, Scenario coverage matrix, Fixtures and datasets, and Load tests and gates under /settings/quality.

Decisions and notes
- Current AIP status: TASKS sections 27 and 31 plan a real pytest suite including the full inspection workflow lifecycle. CI already runs migrations against a throwaway PostGIS container.
- Known gaps (SIMPLIFICATIONS): no frontend test suite yet; the content-type and documents routers lack coverage.
- The owner accepted all six feature scout suggestions: permission-matrix test, offline sync property tests, 5,000-user load test, golden-file tests, hold-point and completion-gate suite, and the mobile browser smoke suite.
- The frontend smoke suite targets the current absence of frontend tests, which leaves field UI regressions undetected.

Open questions
- No conflicting advice. Not yet decided: whether to adopt other market-seen abilities that were not accepted (mutation testing, visual regression beyond the design component library, scheduled chaos and restore drills, retaining test evidence as compliance artefacts, accessibility and performance budgets in CI).

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
