# TESTING-12 — Live-Keycloak session journeys + viewer-seed 403 journey

<!-- hand-edited: merged QA-3 (Part B) per board re-draw 2026-10-17 -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | IDENTITY-03, TESTING-09 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. ADRs: 0005
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), findings **H4** (Part A), **M12** (Part B)

> Part A (was TESTING-12) proves session revocation and SSO logout against real Keycloak; Part B (was QA-3)
> seeds a real viewer and proves the server-403 journey. Both un-skip the same `projects.spec.ts` placeholders,
> so they are one task.

## Part A — live-Keycloak session journeys (review 11 H4)

### Background

IDENTITY-03 moved its live-Keycloak journeys to TESTING-09, which lists them as "Carried forward (non-blocking,
still open)" and is done, so no row owns them. ACCESS-01, ACCESS-02, DESIGN-02 and the TENANCY-01 `/me/tenant`
journey point at the same carry-forward. `e2e/web/shell.spec.ts:97-99` is still skipped "needs IDENTITY-03". The
back-channel test stubs the token verifier, and Keycloak admin logout is tested only over `httpx.MockTransport`.
The Active sessions page has no Playwright journey, cross-tenant check or axe check.

Review 11 M16 (passkey `hwk` sign-in untested) may be folded in here or left on IDENTITY-04 (which now owns the
IDENTITY-07 sign-off assurance work).

### Spec

Session revocation and SSO logout are proven end to end against real Keycloak in `e2e-skeleton`.

- **files**:
  - e2e/web/shell.spec.ts
  - e2e/web/projects.spec.ts
  - e2e/web/ (new session journeys)
  - e2e/playwright.config.ts
  - tracking/tasks/TESTING-09.md (carried-forward list)
- **steps**:
  - 1. Copy TESTING-09's carried-forward list into this file verbatim and own each item.
  - 2. Journeys on compose with real Keycloak: logout ends the SSO session; back-channel logout revokes app sessions; revoking another browser's session; the Active sessions page (main journey, cross-tenant 404, axe).
  - 3. Un-skip or replace the placeholders in `shell.spec.ts:97-99` and `projects.spec.ts:36-42`.
  - 4. Fix `shell.spec.ts:47`: with real sessions assert `__Host-aip_sid` is not JS-readable, instead of `not.toContain("__Host-")` (the `__Host-aip_csrf` cookie is readable by design).
  - 5. Add the TENANCY-01 `/me/tenant` assertion to the skeleton spec (L21).
- **acceptance**:
  - Every TESTING-09 carried-forward item has a passing test or a stated owner.
  - No `test.skip` placeholder that names a done task remains in `shell.spec.ts` or `projects.spec.ts`.
  - The journeys run in `e2e-skeleton` in CI.
- **tests**:
  - **e2e**:
    - sign out → the Keycloak SSO session is gone and re-visiting the app asks for credentials
    - two browsers, revoke the other from Active sessions → its next request is 401
    - Active sessions page: tenant B sees none of tenant A's sessions; axe clean

## Carried forward from TESTING-09 (owned here)

Copied verbatim from [TESTING-09](TESTING-09.md) ("Carried forward from IDENTITY-03 and ACCESS-02"); each item's
owner and test follow the copy.

> - Live Keycloak on compose: after `POST /api/v1/auth/logout` and the queued `identity.revoke_keycloak_sessions` job,
>   Keycloak's admin `get_sessions(carol)` is empty and the next sign-in shows the password form; running the job again
>   succeeds (404 is success). Keycloak admin `user_logout(carol)` calls the back-channel endpoint and her next
>   `GET /api/v1/me` is 401 `SESSION_EXPIRED`.
> - Playwright: sign in as alice and reload (still signed in); from a second context, sign in again and revoke it from
>   the first context's Active sessions page (`/settings/profile/sessions`), so the second context's next navigation
>   lands on `/login`; Logout clears both `__Host-` cookies.
> - The TENANCY-01 (`/me/tenant` per tenant), ACCESS-01 (no roles: abilities empty, a `requires()` route 403) and
>   ACCESS-02 (assign alice `inspector` on P1; abilities for P1 vs P2) journeys.
> - Nobody holds a role after JIT sign-in: the demo/dev bootstrap must give the first kaefer-demo user `tenant_admin`
>   (a tenant-scope `role_assignment` after `seed_default_roles`) before these journeys can create projects.

| Item | Owner | Test |
|---|---|---|
| Logout → the queued job ends the Keycloak SSO session; the next sign-in asks for credentials | TESTING-12 | `e2e/web/sessions.spec.ts` "Sign out ends the aip realm's Keycloak SSO session…" (admin API: this browser's aip-realm session is gone; replaying the authorize request shows the aip sign-in form; the app sends the browser to `/login`). The mock IdP's own session is the customer IdP's, so it is not asserted. |
| Running the revocation job again succeeds (404 is success) | IDENTITY-03 (done) | `identity/tests/sessions/test_sessions_unit.py::test_keycloak_admin_revocation_is_idempotent` |
| Keycloak admin `user_logout` → back-channel → next `GET /me` is 401 `SESSION_EXPIRED` | TESTING-12 | `sessions.spec.ts` "Keycloak's admin sign-out reaches the back-channel endpoint…". Needed a fix: in compose the realm's back-channel URL was `APP_ORIGIN` (`localhost:8080`), which inside the Keycloak container is Keycloak itself; it is now `${AIP_BACKCHANNEL_ORIGIN}` (compose: `http://api:8000`; the demo keeps `APP_ORIGIN`). |
| Sign in and reload (still signed in) | TESTING-12 | `sessions.spec.ts` "real sign-in returns to next with an HttpOnly session cookie…" |
| Revoke a second context from Active sessions → its next navigation lands on `/login` | TESTING-12 | `sessions.spec.ts` "revoking another browser from Active sessions…" (plus the 401, cross-tenant 404 and axe); the page on all three device projects in `sessions-page.spec.ts` |
| Logout clears both `__Host-` cookies | TESTING-12 | `sessions.spec.ts` "Sign out ends the aip realm's Keycloak SSO session…" |
| TENANCY-01 `/me/tenant` per tenant | TESTING-12 | `sessions.spec.ts` "real sign-in returns to next…" |
| ACCESS-01: a `requires()` route 403 with a real session | TESTING-12 | `projects-viewer.spec.ts` (the viewer's `POST /projects` is 403) |
| ACCESS-01: no roles → abilities empty; ACCESS-02: alice `inspector` on P1, abilities P1 vs P2 | ACCESS-05 | API level already: `access/tests` (abilities, project-scope grants). The browser journeys need the Users & Roles UI that assigns roles, so they move to ACCESS-05 (noted on its board row). |
| First kaefer-demo `tenant_admin` bootstrap | TESTING-09 (done) | compose and Coolify `admin-bootstrap`; `access/tests/roles/test_bootstrap_admin_db.py` |

Review 11 M16 (passkey `hwk` sign-in) is not folded in here; it needs a WebAuthn virtual authenticator journey and
stays with the identity carry-forwards (IDENTITY-08).

## Part B — seed a viewer; real-session server-403 journey (merged from QA-3, review 11 M12)

### Background

`e2e/web/projects.spec.ts:36-42` still has `test.skip(true, "needs IDENTITY-03 … ACCESS-02")` although both are done.
The denial test uses the dev stub, and no real-session user without `project.create` is seeded. The MSW unit test for
the 403 branch of `ProjectCreateForm.tsx` is a separate quick fix.

### Spec

The UI's handling of a server-enforced 403 on project create is proven with a real session.

- **files**:
  - identity/tenancy seeds
  - e2e/web/projects.spec.ts
  - e2e/playwright.config.ts
  - .github/workflows/ci.yml, deploy-coolify.yml (E2E_USER_VIEWER)
- **steps**:
  - 1. Seed a kaefer-demo viewer without `project.create`.
  - 2. Add `E2E_USER_VIEWER` (owner adds the demo secret).
  - 3. Turn the skip into a real `@skeleton` test: the viewer submits `/projects/new` and sees the server-denied message.
  - 4. Delete the stale admin-journey skip.
- **acceptance**:
  - The viewer journey runs in `e2e-skeleton` and is green.
  - No stale skip remains in `projects.spec.ts`.
- **tests**:
  - **e2e**:
    - viewer signs in, posts the create form → 403 surfaced as the permission message; no project created
