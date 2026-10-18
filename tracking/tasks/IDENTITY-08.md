# IDENTITY-08 — Identity auth/session events, invite and step-up browser journeys, IDENTITY-02 carry-forwards

<!-- hand-edited: merged AUDIT-06 (Part B) per board slim 2026-10-18 -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | L |
| Depends on | AUDIT-02, IDENTITY-04, TESTING-12 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/IDENTITY-04.md`](IDENTITY-04.md) (tests block) and ADRs 0005, 0010, 0034
3. `apps/api/aip/modules/identity/tests/test_invite_keycloak.py` (the headless journey this extends)

Part B (was AUDIT-06) also reads:

- [`tracking/tasks/AUDIT-02.md`](AUDIT-02.md) (the security stream and its mapping)
- ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md), [0005](../../docs/adr/0005-identity-architecture.md) (auth events come from the app, not Keycloak)

> Part A (was IDENTITY-08) and Part B (was AUDIT-06) both change identity's login, session and JIT paths and both run live-Keycloak journeys on the compose stack, so they share one harness.

## Part A — Invite and step-up journeys in the browser, plus IDENTITY-02 carry-forwards (was IDENTITY-08)

### Spec

Carried forward from IDENTITY-04 (PR for IDENTITY-04): the parts of its test plan that need the
compose stack and a browser, the live step-up journeys, and two IDENTITY-02 carry-forwards.

- **files**:
  - e2e/ (Playwright specs)
  - apps/api/aip/modules/identity/tests/test_invite_keycloak.py
  - apps/api/migrations/versions/<rev>_identity_unregister_email.py
  - apps/api/aip/modules/identity/service.py, oidc.py, jit.py
- **steps**:
  - 1. Playwright on compose: alice (tenant admin, SSO) invites `erin@client.test`; open the Keycloak
    email from Mailpit, set a password and configure TOTP (compute the code from the manual-entry
    secret on the themed page); erin lands on home and the header shows her email.
  - 2. Playwright: alice's session ages past the step-up window (`AIP_TEST_CLOCK_OFFSET`); inviting
    sends her to the mock IdP, which re-prompts (`prompt=login`); on return the retry prompt
    (`identity.stepUp.*`, `apps/web/src/features/identity/step-up.ts`) succeeds.
  - 3. Live (headless) step-up through the app with real sessions: carol (password + TOTP) gets a
    rotated session with a new `authenticated_at`; bob (`acme-oidc`, upstream `amr=['pwd']`) gets 403
    `MFA_NOT_SATISFIED` and keeps his session. Confirm Keycloak forwards `prompt`/`max_age` to the
    customer IdP (the IdPs set `forwardParameters`).
  - 4. IDENTITY-02 carry-forward: SECURITY DEFINER `identity_unregister_email` (same tenant-context
    and local-user checks), called on email change and user delete; the old address no longer resolves.
  - 5. IDENTITY-02 carry-forward (low): normalise emails with NFKC and require ASCII on the whole
    address (`domain_of`, JIT).
- **acceptance**:
  - The two Playwright journeys pass on desktop Chromium, mobile Chrome and iPad WebKit, with a
    cross-tenant check and axe.
  - Carol's and bob's live step-ups behave as above.
  - A changed or deleted local email no longer resolves to its old tenant.
- **tests**:
  - **integration**: unregister on email change and delete; NFKC (Kelvin sign) refused.
  - **e2e**: steps 1 and 2.

## Part B — Identity emits auth and session events into the security stream (merged from AUDIT-06)

### Spec

Split from AUDIT-02 step 5 (2026-10-16), as that step allows: identity emitted no domain events, and
its OIDC callback, logout, back-channel logout, JIT and revoke paths are security code that IDENTITY-04
also changes. AUDIT-02 routes any `auth.*` / `session.*` event to `security_audit_events`; this task
makes identity publish them.

- **files**:
  - apps/api/aip/modules/identity/events.py, manifest.toml (declare the events)
  - apps/api/aip/modules/identity/routes.py, jit.py, sessions.py (one `emit()` each)
- **steps**:
  - 1. Declare `auth.login.succeeded`, `auth.login.failed`, `auth.logout`, `auth.jit_provisioned` and `session.revoked` v1. Payload: `sourceIp`, `device` (user agent), `authStrength`, `targetRef` where it applies; no token or credential ever.
  - 2. Emit each in the transaction that records the outcome. `auth.login.failed` only when the tenant is resolved through `login_directory`; unresolved attempts are logged, never written to a tenant chain.
- **acceptance**:
  - A Keycloak sign-in, project create and sign-out leave `auth.login.succeeded` and `auth.logout` in `security_audit_events` and `project.created` in `audit_log`.
- **tests**:
  - **integration**: each path emits its event once; a failed login for an unknown tenant writes nothing.
  - **e2e**: log in through Keycloak as the kaefer-demo admin, create a project, log out; check both streams.
