# IDENTITY-08 — Invite and step-up journeys in the browser, plus IDENTITY-02 carry-forwards

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | IDENTITY-04, TESTING-12 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`tracking/tasks/IDENTITY-04.md`](IDENTITY-04.md) (tests block) and ADRs 0005, 0010, 0034
3. `apps/api/aip/modules/identity/tests/test_invite_keycloak.py` (the headless journey this extends)

## Spec

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
