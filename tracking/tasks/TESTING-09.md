# TESTING-09 — Walking-skeleton e2e: two tenants, login, register, isolation (CI + staging)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | OPS-09, PROJECTS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. ADRs: 0007 (M0 walking skeleton; this task is its exit proof), 0002 (fail-closed tenant context), 0005 (Keycloak-brokered login, app session cookie), 0004 (`e2e/`, `tests/`)
4. Only if the step needs it: the "Milestone M0" section of [`docs/reviews/07-delivery.md`](../../docs/reviews/07-delivery.md)

## Spec

Prove M0 end to end. A Keycloak user of tenant A signs in to the Next.js shell and creates a project in the register. A user of tenant B signs in, cannot see that project and gets 404 for its id. A query with no tenant context returns 0 rows. The journey runs on every CI build against the compose stack, and as the staging smoke after each deploy.

- **files**:
  - e2e/playwright.config.ts (projects `web` and `staging`)
  - e2e/fixtures/tenants.ts
  - e2e/fixtures/login.ts
  - e2e/web/walking-skeleton.spec.ts
  - tests/isolation/projects-unset-tenant.spec.ts
  - .github/workflows/ci.yml (add job `e2e-skeleton`)
- **steps**:
  - 1. Fixtures: use the tenants seeded by TENANCY-01 (`kaefer-demo`, `tenant-b`) and the realm users from IDENTITY-01's Keycloak import, one admin per tenant (for example `admin@kaefer-demo.test` and `admin@tenant-b.test`). Read credentials from env (`E2E_USER_A`, `E2E_PASS_A`, …) and never hard-code staging secrets. If the realm import has no second-tenant user, add one there; that is the only change allowed outside `e2e/` and `tests/`.
  - 2. In login.ts, `loginAs(page, user)` drives the real flow: `/login`, enter the email, complete the Keycloak form, and land in the shell. Save the storage state per user for reuse inside one run only.
  - 3. In walking-skeleton.spec.ts, tagged `@skeleton @staging`:
    - (a) A logs in, opens Projects, creates `E2E-<runId>` named "Walking skeleton", and sees it in the register with status Draft. Capture its id from the API response.
    - (b) B logs in in a separate browser context and opens Projects. The register does not contain `E2E-<runId>`, and a search for it returns the empty state.
    - (c) B's `page.request.get('/api/v1/projects/<id>')` returns 404 (not 403, not 200).
    - (d) A's own GET of the id returns 200.
    - (e) Afterwards, A archives the project so staging data does not pile up. `runId` = `GITHUB_RUN_ID-<attempt>`, or a timestamp locally.
  - 4. In projects-unset-tenant.spec.ts (Vitest + Testcontainers, CI only, because staging DB access is not allowed from tests): migrate an empty Postgres, insert a project for each of two tenants as the owner, then connect as `aip_app` with no `app.tenant_id` set. `SELECT count(*) FROM projects` is 0. An `INSERT` without a tenant fails the RLS WITH CHECK. With `set_config('app.tenant_id', A, true)` inside a transaction, the count is 1.
  - 5. In ci.yml, add job `e2e-skeleton`: `docker compose up --wait` (api, web, postgres, redis, keycloak), run migrations and seeds, then `pnpm --filter e2e test --project web --grep @skeleton`. Upload the trace, video and HTML report on failure. Make the job a required status check, and give it a 15-minute timeout.
  - 6. Hook into OPS-09: the staging smoke step runs `--project staging --grep @staging` with `BASE_URL` set to the staging URL and staging test-user credentials from GitHub environment secrets. A failure fails the deploy job, so OPS-10 can roll back.
  - 7. Keep the test reliable: no fixed sleeps, web-first assertions only, retries=0 in CI for this spec (a flake is a bug), and each step's assertion message names the M0 property it proves.
- **acceptance**:
  - The `e2e-skeleton` CI job is green on main and required for merge.
  - The same spec passes against staging after an OPS-09 deploy, and its failure blocks the deploy.
  - The unset-tenant check runs in CI and fails if the projects RLS policy is weakened (proven once by a temporary policy change in a draft PR).
  - With this merged and the staging URL live, the M0 exit criteria in ADR 0007 are met. Update BOARD.md's M0 status in the same PR.
- **tests**:
  - **unit**:
    - The `runId` helper with `GITHUB_RUN_ID=123` and `GITHUB_RUN_ATTEMPT=2` returns `123-2`. Without them it returns a value matching `^\d{13}$`.
    - The tenants fixture throws `Missing E2E_USER_B` when that env var is absent, rather than skipping.
  - **integration**:
    - projects-unset-tenant: no context gives a count of 0. An insert with no context throws an RLS violation (SQLSTATE 42501). Tenant A's context gives a count of 1, and tenant B's context gives 1, a different row id.
    - Temporarily replace the projects policy with `USING (true)` in a scratch migration on a branch. Expected: projects-unset-tenant and step (b) of the e2e spec both fail.
  - **e2e** (Playwright):
    - On CI against compose: steps (a) to (e) pass in under 2 minutes, and B never sees `E2E-<runId>`.
    - On staging after deploy: the same spec with `--project staging` passes, and the created project ends archived.
