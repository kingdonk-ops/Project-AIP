# Codebase gap and security review (2026-10-16)

- **Scope:** `origin/main` at `d119e66`. Covers `apps/api`, `apps/web`, `packages/`, migrations, infra, CI.
- **Method:**
  - Read-only. No code changed.
  - Seven parallel reviewers worked from the 62 task specs, the code and the tests. I re-checked every High finding and a sample of the others in the code.
  - Full suites ran in WSL Ubuntu-24.04 with Docker (results in §0).
- **Lens:** OWASP ASVS 4.0.3 L2.
- **Status (updated 2026-10-17):**
  - Findings only; the owner chooses what to act on.
  - **H1:** stopgap done in PR #101; the full fix is SECURITY-11 (see H1).
  - **H2:** done in PR #106.
  - **Owner steps** (demo Keycloak, secrets, signing key): see [11-owner-actions.md](11-owner-actions.md).
  - Every proposed task in §5 is now a board row, and the row edits listed there are applied.

**Effort column:** **quick** means a fix that fits a small PR; **task** means a new board row, drafted in §5; **note** means a note or row edit on an existing task; **owner** means a setting or secret only the owner can change.

---

## 0. Suite results

| Check | Result |
|---|---|
| `ruff check`, `ruff format --check`, `pyright`, `lint-imports`, `gen_permissions --check`, `aip-db lint`, `next_task.py --check` | pass |
| `pnpm -r lint`, `pnpm -r typecheck`, `pnpm -r build` | pass |
| `pnpm -r test` | **2 failures**: `packages/ui/src/register/RegisterTable.test.tsx`, "pages forward and back by cursor…" and "shows the bulk bar…" (both `Test timed out in 5000ms`), 154 pass. Re-run alone: 11/11 pass, so these are timing failures on the slow laptop (default 5 s `testTimeout`), not bugs. **Optional quick fix:** raise `testTimeout` for that file. |
| `pytest` (all, Testcontainers) | pass: **1620 passed, 13 skipped** in 30 min. The skips are the prod-strip image tests and gitleaks, which need images/tools built by `security.yml`, so expected locally. |
| `pnpm audit --prod` | 1 high: `braces` ≤3.0.3 (GHSA-vfj7-8cjw-p6xm), via `config-eslint > eslint-plugin-boundaries`. Already accepted in `config/vuln-exceptions.txt:7-8` (lint-time only, expires 2027-01-05). No new action. |
| `pip-audit` | pass: no known vulnerabilities (workspace packages excluded). |
| `tools/sbom.sh` (licence policy) | pass: Python and JS SBOMs written, licence policy green. The image SBOM path is unproven (M15). |

---

## 1. High

### H1. Anyone can sign in to the public Coolify demo as tenant admin of both tenants (security)
- **Evidence:**
  - The repo is **public** (`gh repo view` → `PUBLIC`).
  - The users and their passwords are committed in [`infra/keycloak/realm-mock-idp.json:60,71`](../../infra/keycloak/realm-mock-idp.json): `alice@kaefer.test` / `alice_dev_only_password` and `bob@acme.test` / `bob_dev_only_password`. Line 11 of that file says "Never import outside local dev and CI".
  - That realm is built into the demo image: [`infra/coolify/images/keycloak.Dockerfile:7`](../../infra/coolify/images/keycloak.Dockerfile).
  - The realm is publicly routed by [`infra/coolify/nginx.conf:48`](../../infra/coolify/nginx.conf), which allows `^/auth/(realms/(aip|mock-idp)|resources)/`.
  - `admin-bootstrap` makes both users `tenant_admin`: [`infra/coolify/docker-compose.coolify.yml:310-323`](../../infra/coolify/docker-compose.coolify.yml).
- **Impact:**
  - Anyone who reads GitHub can get full admin of both demo tenants. The data is synthetic, but the demo is internet-facing (ASVS 2.10.4, 14.1).
  - The mock-IdP account console is reachable and both brokers have `trustEmail=true`. So a signed-in user can change their email and mint new "verified" identities.
- **Fix:**
  - Build a demo-only mock-IdP realm with no users, and create the users at deploy time from Coolify secrets (or set their passwords from env).
  - Block `/auth/realms/mock-idp/account` in the demo nginx.
  - Rotate the demo passwords and `E2E_PASS_A/B`.
  - Optional: put Traefik basic auth or an IP allow-list in front of the demo.
- **Effort:** task SECURITY-11. Blocking the account console and rotating the passwords is a quick fix you could do today.
- **Status:** stopgap done in PR #101.
  - The mock-IdP realm disables the `UPDATE_PROFILE`, `UPDATE_EMAIL`, `VERIFY_PROFILE`, `UPDATE_PASSWORD` and `CONFIGURE_TOTP` required actions.
  - The user profile makes username, email and names admin-edit only.
  - The demo nginx returns 404 for the mock-IdP account console.
  - The live demo still needs the owner's `kcadm` step described in PR #101, because Keycloak does not re-import an existing realm.
  - The committed passwords and the users in the image remain. SECURITY-11 is the full fix.

### H2. Suspended or offboarded tenants keep access to several tenant-scoped routes (TENANCY-01 criterion unmet)
- **Criterion:** "A suspended tenant gets 403 on every tenant-scoped route" ([`TENANCY-01.md:46`](../../tracking/tasks/TENANCY-01.md)).
- **Evidence:**
  - Tenant status is checked only by `require_active_tenant`. That dependency is used only by the access/roles, identity `/me`, ops `platform_tenants`, projects, tenancy and uploads routers.
  - The session resolver and the `authenticated()`/`requires()` guards never check tenant status ([`platform/access/dependencies.py:110-155`](../../apps/api/aip/platform/access/dependencies.py)).
  - Routes with no tenant-status check:
    - `PUT /settings/flags/{flag}` and `GET /settings/flags` ([`platform/flags/routes.py:53,64`](../../apps/api/aip/platform/flags/routes.py)). The PUT writes data and emits an outbox event.
    - `GET /access/me/abilities` ([`modules/access/routes.py:23`](../../apps/api/aip/modules/access/routes.py)).
    - The event catalogue, deprecate and dead-letter routes ([`platform/events/routes.py:130,163,185`](../../apps/api/aip/platform/events/routes.py), [`dead_letter_routes.py:77,96,128`](../../apps/api/aip/platform/events/dead_letter_routes.py)).
    - `GET /terms/coverage`.
  - The test that claims coverage, `tenancy/tests/test_access.py:209`, only walks routes that already carry the guard.
- **Impact:** a live session in a suspended tenant can still toggle feature flags and read data (ASVS 4.1.1, 4.2). Later suspension (ENT-03) and offboarding (TENANCY-07) will inherit the hole.
- **Fix:**
  - Attach `require_active_tenant` to every non-`public()` route in one place: in `aip.main` or through an access hook, since platform cannot import modules.
  - Add a route-walk test that fails when a non-public route lacks the check, plus a suspended-tenant test on `PUT /settings/flags/bim`.
- **Effort:** quick, about half a day including tests.
- **Status:** done in PR #106. Every authenticated route now refuses an inactive tenant.

### H3. Job handlers run as `aip_jobs`, which cannot write any domain table or emit events. This blocks UPLOADS-02 (integration)
- **Evidence:**
  - Handlers run inside `with_tenant(tenant_id, engine=get_jobs_engine())` ([`modules/ops/runner.py:141,166-168`](../../apps/api/aip/modules/ops/runner.py)), as ADR 0016 describes.
  - `aip_jobs` has only SELECT and column UPDATE on `domain_events`, with **no INSERT** ([`db/schema.snapshot.sql:66-78,241`](../../db/schema.snapshot.sql)). It has SELECT and UPDATE on `jobs`, plus its queue tables.
  - The table templates grant nothing to `aip_jobs` ([`db/templates/tenant_table.sql.tpl:40-41`](../../db/templates/tenant_table.sql.tpl)).
- **Impact:**
  - The only handler today (`identity.revoke_keycloak_sessions`) only calls Keycloak, so nothing breaks yet.
  - UPLOADS-02 updates `upload_sessions` and emits `upload.completed`/`upload.rejected` inside its job (UPLOADS-02.md:45,57,62). Every scan would get `permission denied`, retry until it dead-letters, and leave uploads stuck in quarantine. The same will happen to AUDIT-03, imports and PDF jobs.
  - No test catches it: the runner tests' handlers only touch `jobs`.
  - This is the generalisation of the `domain_events` INSERT problem you had already found.
- **Fix:** decide in an ADR 0016 amendment between two options:
  - (a) Run the handler transaction on the `aip_app` engine (RLS still applies through `with_tenant`) and keep `aip_jobs` for queue and status bookkeeping.
  - (b) Grant `aip_jobs` the `aip_app` table set and INSERT on `domain_events`.

  Option (a) is simpler and keeps least privilege. Either way, add a runner test whose handler writes a tenant table and emits an event.
- **Effort:** task OPS-17. Add OPS-17 to UPLOADS-02's dependencies.
- **Status (2026-10-17):** OPS-03 (PR #100, after this review's snapshot) granted `aip_jobs` INSERT on `domain_events`. The tenant-table grants are still missing, so OPS-17 stands.

### H4. Session revocation and SSO logout are not proven end to end, and the carried-forward e2e has no owner
- **Evidence:**
  - IDENTITY-03 moved its live-Keycloak journeys to TESTING-09 ([`IDENTITY-03.md:166-169`](../../tracking/tasks/IDENTITY-03.md)). Those journeys are logout ends the SSO session, back-channel logout revokes app sessions, revoking another browser's session, and the Active sessions page.
  - TESTING-09 lists them as "Carried forward (non-blocking, still open)" (TESTING-09.md:59-71, 90-91) and is marked done. No board row owns them. ACCESS-01, ACCESS-02, DESIGN-02 and the TENANCY-01 `/me/tenant` journey point at the same carry-forward.
  - [`e2e/web/shell.spec.ts:97-99`](../../e2e/web/shell.spec.ts) is still `test.skip(true, "needs IDENTITY-03 …")`, although IDENTITY-03 is done.
  - The back-channel test stubs the token verifier (`identity/tests/sessions/test_sessions_db.py:214-252`), and Keycloak admin logout is tested only over `httpx.MockTransport`.
  - The Active sessions page (`routes/_app/settings/profile/sessions.tsx`) has no Playwright journey, cross-tenant check or axe check, which AGENTS.md:53 requires.
  - `shell.spec.ts:47` (`not.toContain("__Host-")`) runs only against the dev stub. With real sessions it would wrongly fail, because the JS-readable `__Host-aip_csrf` cookie is there by design. The real assertion should be that `__Host-aip_sid` is absent.
- **Impact:** session revocation and IdP logout are security controls (ASVS 3.3, 3.5), and nothing shows they work against real Keycloak.
- **Fix:**
  - Add a single task that owns the TESTING-09 carry-forward list verbatim, run in `e2e-skeleton` on compose.
  - Un-skip or replace the placeholders in `shell.spec.ts` and `projects.spec.ts`.
- **Effort:** task TESTING-12.

---

## 2. Medium

| # | Finding | Evidence | Impact | Fix | Effort |
|---|---|---|---|---|---|
| M1 | The client IP behind a proxy is the proxy's IP, so the login rate limit becomes a global lockout | `apps/api/Dockerfile:99`: uvicorn runs without `--proxy-headers`/`--forwarded-allow-ips`. `identity/routes.py:133` keys the 10/min limit on `request.client.host`, and `login_session.py:28` stores it as the session IP. `apps/web/nginx.conf:25` forwards a client-spoofable `$proxy_add_x_forwarded_for` (the Coolify nginx does use realip correctly). | Behind the ALB (ADR 0026), ten requests a minute from anyone block every user's sign-in. Session and audit IPs are useless (ASVS 11.1.4, 7.1). | Set `FORWARDED_ALLOW_IPS` to the ALB/VPC CIDR and pass `--proxy-headers`. Port the realip block to `apps/web/nginx.conf`. Add a test that `client.host` comes only from a trusted hop. | quick |
| M2 | No request-body size cap and no security headers on the ALB→API path; ADR 0026's HSTS claim is untrue | No body-size middleware exists. ADR 0026:19-20 routes `/api/*` straight to the API. The API sends no `nosniff`, `frame-ancestors`/`X-Frame-Options` or HSTS. ADR 0026:28 says nginx sends HSTS, but `apps/web/nginx.conf` has none. | Memory DoS through large JSON bodies. Missing defence-in-depth headers (ASVS 13.1.3, 14.4). | Add an ASGI middleware that caps bodies (about 1 MiB; uploads use presigned POST, so the API never needs more). Add a security-headers middleware. Add HSTS to the web nginx, and extend `tools/tests/test_nginx_headers.py`. | task SECURITY-12 |
| M3 | `aip_readonly` can read every tenant's PII and session metadata | All policies key on `current_setting('app.tenant_id', true)`, which any role can set with `set_config`. `aip_readonly` has SELECT on `user_session` (ip, user_agent, kc_sid), `app_user`, `auth_event`, `audit_log`, `security_audit_events` and `breach_incidents`. `db/bootstrap/00_cluster.sql:66` says "RLS limits what it reads". | Anyone holding the reporting login (a BI tool or an analyst) can loop over tenant ids and dump every tenant's users and session data (ASVS 4.1.3, 8.3.4). | Revoke `aip_readonly` on the session, auth and PII tables. Serve reporting through security-barrier views or `SECURITY DEFINER` aggregates. Amend ADR 0012 to say that for roles running arbitrary SQL, RLS is advisory. | task SECURITY-13 |
| M4 | The realm-as-code falls back to publicly known client secrets, including the `manage-users` service account | `infra/keycloak/realm-aip.json:622,691`: `${AIP_API_CLIENT_SECRET:aip_api_dev_only_secret}` and `${AIP_ADMIN_CLIENT_SECRET:aip_admin_dev_only_secret}`. `aip-admin` holds `manage-users`. `IdentitySettings` refuses the dev cookie key only when `AIP_ENV == "production"`, a denylist (`settings.py:63-67`). Coolify is safe today because it uses `${VAR:?}`. | Any Keycloak import without the env var makes `client_credentials` with a public secret work on the public token endpoint. That means user takeover in every tenant (ASVS 2.10.4). | The API refuses to start with any known dev secret unless `AIP_ENV` is `development` or `test` (an allowlist). Use a deployed-realm overlay with no defaults, or a post-import check. | quick (API check), then task SECURITY-14 (realm overlay) |
| M5 | Unauthenticated `/platform/version` and `/health/ready` open fresh DB connections and disclose versions | `platform/version/routes.py:72-115` calls `asyncpg.connect()` on every request and returns the Postgres, Python and library versions and the git SHA. `modules/ops/health.py:116-136,188` opens two connections plus Redis on every request. Both are public in production. | Anonymous connection exhaustion denies service to the app, the jobs and the audit writer. Fingerprinting (ASVS 14.3.3). | Cache the Postgres version for the process lifetime and the readiness result for a few seconds. Drop dependency versions from the public body, or require `authenticated()`. Restrict `/ready` at ingress. | quick |
| M6 | The Coolify deploy is not gated on the security scans; three demo images are never scanned; the deploy job uses tag-pinned actions while holding secrets | `deploy-coolify.yml:41-62` builds, pushes and deploys on every push to main without depending on `security.yml`. The keycloak, postgres and migrator demo images are never Trivy-scanned or SBOM'd. Lines 118-120 pin actions by tag (`security.yml` pins by SHA). Cosign signs local image ids and falls back to an ephemeral key (`security.yml:173-179`). | A vulnerable or unsigned image reaches the internet-facing demo (ASVS 14.2, 10.3.2). | Gate the deploy on the security jobs. Scan all five demo images. SHA-pin the actions. Sign the pushed registry digests. Fail on `main` when `COSIGN_PRIVATE_KEY` is missing. | task SECURITY-15 |
| M7 | Release flags never consult `EntitlementService` (ENT-01 and ARCH-08 criteria unmet) | `platform/flags/dependency.py:46-48` falls back to `AllowAllEntitlements` unless `app.state.flag_entitlements` is set, and nothing sets it outside tests. ENT-01.md:41,64 says a route is reachable only when both the entitlement and the flag allow it. The only test (`tests/platform/flags/test_flags.py:125`) asserts the stub itself. | The first `requires_flag("bim")` route opens for tenants without `feature.bim`. No production route uses it yet. | In `create_app`, set `flag_entitlements` to an adapter that calls `EntitlementService.check(tenant, "feature.<flag>")`. Test it through the bim probe for a `core` tenant. | quick |
| M8 | CI never runs the event-schema exporter (ARCH-06 criterion unmet) | No `export_event_schemas` in `.github/`. `tests/platform/events/test_registry.py:132-135` relies on "exporter + CI git-diff", which does not exist. | A new event or version can ship without being frozen, and its payload can later change silently. | Add a CI step that runs the exporter, then `git diff --exit-code packages/contracts/events`. Fail on untracked files too. | quick |
| M9 | No tenant fan-out for periodic jobs: upload-session expiry and entitlement snapshots never run | `UploadSessionService.expire_stale_sessions` (`uploads/service.py:248-251`) is called only by a test, although UPLOADS-01 step 7 says it is scheduled. `snapshot_cli` needs explicit `--tenant` ids because `aip_jobs` cannot list tenants (`entitlements/snapshot_cli.py:19`). Nothing schedules either. | Stale upload sessions never expire. `tenant_usage` is never snapshotted. Expired overrides are never swept, so no audit event is written for them (enforcement is still correct). | Add a `SECURITY DEFINER` `platform_active_tenant_ids()` executable by `aip_jobs`, and a fan-out periodic job that enqueues one job per tenant. | task OPS-18 |
| M10 | Nothing proves the worker or outbox run in the stack, CI or the demo | The worker healthcheck is `python -c "import aip"` (`infra/docker-compose.yml:399-403`, same in Coolify). `tools/smoke.py:68-89` and `walking-skeleton.spec.ts` never check that `project.created` is published or audited. The CI e2e log tail omits `worker` (`ci.yml:466`). | A crash-looping worker, a wrong `DATABASE_AUDIT_WRITER_URL`, or a dispatcher that never drains all ship green, and the demo audit trail silently stops. | Make the worker healthcheck real (a heartbeat). After the skeleton e2e, assert `published_at` is set and an `audit_log` row exists. Add an outbox-lag smoke check. | task TESTING-13 |
| M11 | The UPLOADS-01 e2e is skipped in every CI lane | `e2e/web/uploads-presign.spec.ts:67` uses `(users ? test.describe : test.describe.skip)`. The default lanes set no users. The credentialed lanes use `testMatch: SKELETON` = `walking-skeleton.spec.ts` only (`e2e/playwright.config.ts:48-57`). | It passes forever while proving nothing. The RustFS integration tests do cover the policy. | Tag it `@skeleton @staging` and add it to the skeleton `testMatch`. Optionally list the bucket prefix after the tamper attempt. | quick |
| M12 | The PROJECTS-02 server-403 path is untested, and its placeholders are still skipped | `e2e/web/projects.spec.ts:36-42` still has `test.skip(true, "needs IDENTITY-03 … ACCESS-02")`, although both are done. The denial test uses the dev stub. The 403 branch at `ProjectCreateForm.tsx:99-102` has no unit test. No real-session user without `project.create` is seeded. | The UI's handling of server-enforced denial is unproven. | (a) Add an MSW unit test (quick). (b) Seed a kaefer-demo viewer and `E2E_USER_VIEWER`, then turn the skip into a real `@skeleton` test. Delete the stale admin-journey skip. | quick + task QA-3 |
| M13 | Project detail, edit and archive pages and site management have no UI and no owning task | `GET/PATCH /projects/{id}` and site CRUD exist (`projects/routes.py:77-164`). The web uses only list, create and sites-list. There is no `/projects/$projectId` route. AUDIT-04 step 5 assumes a detail page exists. | Users can't open, edit or archive a project, or manage sites, and AUDIT-04 has nowhere to put its tab. | New page using RecordDetail. | task PROJECTS-07; add it to AUDIT-04's dependencies |
| M14 | DESIGN-07 and DESIGN-14 layout criteria are untested | DESIGN-07.md:51-52 wants the computed font and button colour checked on the Keycloak page; the only `getComputedStyle` is on the app's own fixture page (`e2e/web/ui-fixture.spec.ts:23`). DESIGN-14.md:40 wants a 60-character name kept inside the viewport at 1440px and 390px; no viewport test exists, and the jsdom class check has no layout. | Wrong theme selectors, or a header that overflows on mobile, would stay green. | Add two Playwright assertions to the skeleton/login fixture and a long-name viewport test. | quick |
| M15 | STACK-04's release path has never run; the sandbox image is never SBOM'd | `gh run list --workflow release.yml` is empty. `release.yml` globs `apps/sandbox/*/Dockerfile`, but the only file is `apps/sandbox/Dockerfile`, so `image-sandbox-*.cdx.json` (the scope of ADR 0011's LGPL rule) is never produced. | The OS-package licence rules have never run end to end. | Fix the glob, then push `v0.0.0-sbomtest` once (or add a `workflow_dispatch` dry run). | quick + owner |
| M16 | IDENTITY-01's passkey (`hwk`) sign-in path is untested | IDENTITY-01.md:77,112. Only static realm lint and unit tests mention `hwk`; no WebAuthn journey exists. | IDENTITY-07 sign-off assurance counts passkeys, but nothing proves the flow. | Add a CDP virtual-authenticator Playwright journey. | note on IDENTITY-07 (or fold into TESTING-12) |
| M17 | The `uploads.view` permission is declared but never checked | `uploads/manifest.toml`. `uploads/routes.py:85-102` checks only requester or `uploads.admin`. The default role matrix still grants `uploads.view`. | The role editor (ACCESS-05) will show a permission that does nothing. | UPLOADS-06 checks it on list and status, or it is removed. | note on UPLOADS-06 |

---

## 3. Low

Most of these are quick fixes. Grouped by area.

### Security, defence in depth
- **L1. Operator `platform.*` codes are enforced only in `RoleService`.** `role_permission` has no CHECK constraint, and `RoleGrantProvider` does not filter these codes ([`access/roles/grant_provider.py:26-38`](../../apps/api/aip/modules/access/roles/grant_provider.py)). Any write path that bypasses the service would grant a tenant user the cross-tenant operator routes. Fix: a migration adding `CHECK (permission_code NOT LIKE 'platform.%')`, plus a filter in the provider. Effort: quick.
- **L2. `aip_app` has an unused hard-DELETE grant** on `app_user`, `tenant_membership` and `jobs`. It comes from `tenant_table.sql.tpl:40`, and the platform soft-deletes. Fix: revoke it, and change the template so it grants only SELECT, INSERT and UPDATE. Effort: quick.
- **L3. `POST /uploads/sessions` doesn't check that `body.project_id` exists in the tenant**, and there is no FK ([`uploads/routes.py:57-64`](../../apps/api/aip/modules/uploads/routes.py), snapshot:3446). No cross-tenant read is possible because RLS holds, but later project-scoped `uploads.admin` checks trust the stored id. Fix: call `ProjectsApi().get_project` and add a composite FK. Effort: quick.
- **L4. Dev and prod gating uses denylists.**
  - `/docs` and `/openapi.json` are disabled only when `env == "production"` (`main.py:152-161`).
  - The seeds refuse only `"production"` (`tenancy/seed.py:112`, `identity/seeds.py:47`).
  - The strip manifest lacks `/api/v1/_fixtures`.
  - `check_prod_strip.py:269` doesn't check `demo`.
  
  None of this is reachable externally today. Fix: switch to allowlists and add the manifest line. Effort: quick.
- **L5. Log scrubber gaps.** It misses OIDC `code=`/`state=`, `sid`/`kc_sid`/`csrf` keys (`observability/scrub.py:34-54`); nothing logs them today. Keycloak login and admin events are not enabled in `realm-aip.json` (ASVS 7.2.1). Effort: quick.
- **L6. Unneeded OAuth redirect URI.** `${APP_ORIGIN}/login` is listed in `aip-api` `redirectUris` but never used. If it were used, the authorization code would land in the SPA URL and history. Fix: remove it. Effort: quick.
- **L7. `GET /settings/organisations` has no limit or pagination** (`tenancy/organisations/routes.py:45-49`). Effort: quick.
- **L8. A personal email address is in a committed doc** (`docs/handover/CLAUDEK-HANDOVER.md:44`). Remove it if unwanted; a history rewrite isn't worth it. Effort: quick.
- **L9. `RUNTIME_ROLES` omits `aip_audit_writer`** ([`platform/db/schema_guard.py:44`](../../apps/api/aip/platform/db/schema_guard.py)), so the privilege-posture check never inspects it. `aip_readonly` has no user and no dev password. Effort: quick.
- **L10. Non-admins can self-assign roles (design note).** A non-admin holder of `access.role_assignment.manage` can assign non-privileged roles to themselves. Today only `tenant_admin` holds the code. Fix: add a line to ADR 0020 stating this is intended. Effort: note.

### Integration and runtime
- **L11. Worker start-up gaps.**
  - The worker's compose `depends_on` lacks `valkey`.
  - The audit-writer engine is never disposed on shutdown (`worker.py:108-117`).
  - Nothing probes the audit-writer login at start-up.
  
  Effort: quick.
- **L12. No test dispatches through the real subscriber set.** No test runs `active_subscribers()` (audit plus terms together) through `dispatch_batch`; the tests use hand-built registries (`audit/tests/test_writer_db.py:63-66`). Effort: quick (one test).

### Tests that prove less than they claim
- **L13.** The TESTING-01 unit test "`set_config` exactly once per transaction" (the `before_cursor_execute` listener) and the `integration` marker don't exist. Effort: quick.
- **L14.** The ARCH-09 e2e mocks every admin API call with `page.route`. The ARCH-06 live check (operator 200, tenant 403) was never run against a stack; the httpx tests cover the API side. Effort: quick.
- **L15.** AUDIT-01: the TRUNCATE probe for `aip_app` is missing (`audit/tests/test_grants_db.py:31-37`), and `audit/tests/e2e_chain.py` is never run by CI. Effort: quick.
- **L16.** DESIGN-06's `@ts-expect-error` test checks a local helper, not `registerNavItem` (`shell/__tests__/units.test.ts:27-31`). Effort: quick.
- **L17.** DESIGN-01's built-CSS `--accent:#0f766e` check is missing from CI. Effort: quick.
- **L18.** The PROJECTS-02 e2e doesn't assert the `?created=` URL or run axe on the permitted create form. The PROJECTS-01 generated-client script is absent. Effort: quick.
- **L19.** `version/test_version.py:87` still treats Procrastinate as optional. Effort: quick.
- **L20.** OPS-02's export-job e2e has no owner. Effort: note, carry it to OPS-03.
- **L21.** The TENANCY-01 `/me/tenant` Keycloak journey is missing. Effort: quick, one assertion in the skeleton spec.

### Spec deviations and documentation
- **L22.** IDENTITY-01: the first sign-in after TOTP enrolment gives `acr=aal2` with `amr=[pwd]` (`test_keycloak_flows.py:329-331`). Downstream code (IDENTITY-04, IDENTITY-07) should key on `acr`. Effort: note.
- **L23.** DESIGN-14: under 768px the name is ellipsised rather than dropped, and the tooltip threshold (24 characters, `brand.ts:10`) differs from the CSS truncation (32ch). Effort: quick, or fold into DESIGN-08.
- **L24.** Stale "until X" notes whose X has landed:
  - `main.py:24-25` (ACCESS-02).
  - `identity/principal.py:12,86`, `jit.py:384-391`, and `api.py:98-116` `PlaceholderLoginHandler`, which is exported but test-only (IDENTITY-03).
  - `e2e/web/stub-session.ts:3` and `projects.spec.ts:3-4` (IDENTITY-03).
  - The projects and uploads test conftests still use a test grant provider "until ACCESS-02".
  - `tenancy/events.py:5-7` names a subscriber that doesn't exist.
  - `access/api.py:48-54` and `identity/api.py:127-133` keep the template `get_api()` raising `NotImplementedError`.
  - `docs/blueprint/01-decisions.md:45` gives ADR 0006 as proposed.
  
  Effort: quick, one docs-and-cleanup PR.
- **L25.** Orphaned term keys: `shell.header.search`, `shell.header.tenantLogo`, `shell.header.projectSwitcher`, `projects.error.invalid`, `ui.workflow.current`, `shell.nav.projects`. There is also a duplicate seeded projects nav item (`nav-registry.ts:24-27`). Effort: quick.
- **L26.** Feature flags have no web consumer: nav items can't be flag-gated and there is no flags admin page. ARCH-08 left this to "the web shell task", which doesn't exist. Effort: task DESIGN-15.
- **L27.** `GET /terms/coverage` has no UI. Effort: note, add it to TERMS-08's scope.
- **L28.** ARCH-09's out-of-scope list (replay, CSV export, tenant dead-letter view) has no board rows. Effort: note on OPS-12, or accept as backlog.

### Owner actions
- **O1.** Add the `E2E_USER_A/B` secrets: without them `deploy-coolify.yml:136-139` exits 0 and the demo deploy is unverified. Make `e2e-skeleton` a required check.
- **O2.** Add `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD`.

---

## 4. Checked and sound

- **Access framework:**
  - It fails closed: start-up refuses any route without `public()`, `authenticated()` or `requires()`, and `AccessCheckedRoute` returns 403 at runtime for routes added later.
  - `PolicyService` denies unknown codes and other tenants.
  - `X-Project-Id` is always denied until PROJECTS-03.
- **Route authorisation:** every route was checked (the full table is in the reviewer notes). IDOR on sessions and upload sessions gives 404. Assigning a role across tenants is blocked by RLS and a composite FK. `extra="forbid"` on every request model prevents mass assignment.
- **RLS:**
  - Every tenant table has ENABLE plus FORCE RLS, and a fail-closed `NULLIF(current_setting(...,true),'')::uuid` policy with WITH CHECK.
  - The append-only tables have triggers, and only `aip_audit_writer` can write audit.
  - Every `SECURITY DEFINER` function pins `search_path` and revokes PUBLIC.
- **SQL:** no attacker-controlled interpolation. The tenant is always a bind parameter. plpgsql uses `format('%I'/'%L')`.
- **Secrets:** gitleaks scans full history. A history grep found no cloud, VCS or JWT keys. No `.env` files are committed. Coolify requires every secret with `${VAR:?}`. H1 and M4 are the exceptions.
- **OIDC and sessions:**
  - The login flow checks state, nonce, PKCE S256, the RFC 9207 iss and an algorithm allowlist.
  - Back-channel logout is signed and has a body cap. The return-to sanitiser is sound.
  - Cookies use the `__Host-` prefix with Secure, HttpOnly (sid) and SameSite=Lax. The sid is rotated on login and stored only as a hash.
  - Unsafe methods need an Origin match and a double-submit CSRF token.
  - JIT provisioning never trusts browser input for the tenant.
- **Test stubs:** the auth test stub needs both `AIP_ENV=test` and `AUTH_TEST_STUB=1`. The debug routes mount only in test. The web dev stub is stripped and checked in `dist`.
- **Uploads:** the presign policy pins the size range, the Content-Type and the key.
- **CSV export:** guarded against formula injection.
- **Errors:** responses are generic, with no tracebacks, SQL or echoed tokens.
- **Web headers:** the nginx config has a strict CSP.
- **CORS:** none, so same-origin only.
- **Logging:** the access log omits the query string and IP, and the scrubber runs last.
- **Wiring:**
  - Every emitted event is registered, and every subscriber is listed in its manifest.
  - Subscribers run as `aip_app`, the audit writer has full grants, and every worker path binds the tenant.
- **API client and nav:**
  - All 52 generated client operations match the routers, and every web call targets a real endpoint.
  - Every nav entry resolves to a registered route.
- **CI skips:** the Postgres, Redis, Keycloak and RustFS fixtures `pytest.fail` under `CI` rather than skipping. No `unittest.mock` is used anywhere.

---

## 5. Draft board rows

| ID | Title | Module | Size | Depends on | Status | Notes |
|---|---|---|---|---|---|---|
| [SECURITY-11](../../tracking/tasks/SECURITY-11.md) | Demo mock-IdP users from secrets, not committed passwords; block the mock-IdP account console (stopgap done in PR #101) | security | S | OPS-11 | todo | review 11 H1: the repo is public, and alice and bob are tenant_admin on the demo with committed passwords; rotate E2E_PASS_A/B |
| [OPS-17](../../tracking/tasks/OPS-17.md) | Job handlers can write domain tables and emit events (handler role, ADR 0016 amendment) | ops | S | OPS-02, ARCH-05 | todo | review 11 H3: handlers run as aip_jobs, which has no tenant-table grants and no INSERT on domain_events; blocks UPLOADS-02 |
| [TESTING-12](../../tracking/tasks/TESTING-12.md) | Live-Keycloak session journeys: logout ends SSO, back-channel revokes, Active sessions page (cross-tenant + axe), real-session shell | testing | M | TESTING-09, IDENTITY-03 | todo | review 11 H4: owns TESTING-09's carried-forward list verbatim; un-skip shell.spec.ts:97 and projects.spec.ts:36-42 |
| [SECURITY-12](../../tracking/tasks/SECURITY-12.md) | API edge hardening: body size cap, security headers, HSTS in the web nginx | security | S | OPS-04 | todo | review 11 M2: ADR 0026 says nginx sends HSTS, but it does not |
| [SECURITY-13](../../tracking/tasks/SECURITY-13.md) | Least-privilege aip_readonly: revoke session, auth and PII tables; reporting views; ADR 0012 amendment | security | M | DATABASE-07 | todo | review 11 M3: set_config makes RLS advisory for roles running arbitrary SQL |
| [SECURITY-14](../../tracking/tasks/SECURITY-14.md) | Refuse dev secrets outside dev/test (API allowlist check + deployed realm overlay without defaults) | identity | S | IDENTITY-03 | todo | review 11 M4: aip-admin (manage-users) falls back to aip_admin_dev_only_secret |
| [SECURITY-15](../../tracking/tasks/SECURITY-15.md) | Gate the Coolify deploy on the security scans; scan and sign all pushed demo images; SHA-pin deploy actions | ops | S | OPS-11, SECURITY-08 | todo | review 11 M6 |
| [OPS-18](../../tracking/tasks/OPS-18.md) | Tenant fan-out for periodic jobs (tenant id lister for aip_jobs); schedule upload expiry and entitlement snapshot | ops | S | OPS-13, OPS-17 | todo | review 11 M9: expire_stale_sessions and snapshot_cli never run |
| [TESTING-13](../../tracking/tasks/TESTING-13.md) | Stack proves the worker: real healthcheck, outbox drained and audited after the skeleton e2e, outbox-lag smoke | testing | S | TESTING-09, AUDIT-02 | todo | review 11 M10: worker health is `import aip` |
| [QA-3](../../tracking/tasks/QA-3.md) | Seed a kaefer-demo viewer; real-session server-403 journey for /projects/new | testing | XS | TESTING-09 | todo | review 11 M12; adds the E2E_USER_VIEWER secret |
| [PROJECTS-07](../../tracking/tasks/PROJECTS-07.md) | Project detail page (RecordDetail, edit, lifecycle/archive) and sites register with create/edit/delete | projects | M | DESIGN-04, PROJECTS-06 | todo | review 11 M13; AUDIT-04 mounts its History tab here, so add PROJECTS-07 to AUDIT-04's dependencies |
| [DESIGN-15](../../tracking/tasks/DESIGN-15.md) | Nav items honour release flags (GET /settings/flags) and a Settings page to switch them (tenant.flags.manage) | design | S | ARCH-08, DESIGN-06 | todo | review 11 L26 |

**Edits to existing rows** (applied 2026-10-17):
- UPLOADS-02: add OPS-17 to Depends on.
- AUDIT-04: add PROJECTS-07 to Depends on.
- UPLOADS-06: note "check `uploads.view`" (M17).
- IDENTITY-07: note "WebAuthn/`hwk` journey; key on `acr`, not `amr`" (M16, L22).
- TERMS-08: note "coverage report view" (L27).
- OPS-03: note "carry the OPS-02 export-job e2e" (L20).

## 6. Suggested order

1. **Today:**
   - H1 stopgap: block the mock-IdP account console and rotate the demo passwords. *(Done in PR #101, except the password rotation, which moves to SECURITY-11.)*
   - H2: the tenant-status guard. *(Done in PR #106.)*
   - M1: proxy headers.
   - M5: cache the version and readiness checks.
2. **Before UPLOADS-02:** OPS-17.
3. **Quick-fix sweep PR:** M7, M8, M11 and M14, plus the L1-L9 and L24 quick fixes.
4. **Board:** add the rows above *(done 2026-10-17)*, then SECURITY-11 and TESTING-12 next.
