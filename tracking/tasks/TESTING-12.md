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
