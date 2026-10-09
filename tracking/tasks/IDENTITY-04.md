# IDENTITY-04 — Invite/accept via Keycloak admin API; MFA enforcement and step-up
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); identity per ADR 0005 rev 2 -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, IDENTITY-03, STACK-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md) (ignore every WorkOS reference: ADR 0005)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0005](../../docs/adr/0005-identity-architecture.md) rev 2 (Keycloak holds staff passwords and MFA; the app invites through the admin API and checks acr/amr), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (atomic job enqueue), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/identity/data-model.md) (table `user_invite`; ignore `mfa_credential`, which Keycloak now holds), the `python-keycloak` docs (`create_user`, `send_update_account`), and Keycloak 26 docs on ACR / step-up

## Spec

Let tenant admins invite staff who do not sign in through company SSO. The backend creates the Keycloak user through the admin API with required actions (verify email, set password, configure OTP), and Keycloak sends the email. The app keeps `app_user`, `tenant_membership` and `user_invite`. The backend also enforces MFA: it checks `acr`/`amr` on every ID token and requires a fresh second factor (step-up) for critical actions. The backend stores no password, TOTP secret or WebAuthn credential, and imports no `argon2-cffi`, `pyotp` or `webauthn` for staff.

- **files**:
  - apps/api/migrations/versions/<rev>_identity_invites.py
  - apps/api/aip/modules/identity/tables.py
  - apps/api/aip/modules/identity/invites.py
  - apps/api/aip/modules/identity/keycloak_admin.py
  - apps/api/aip/modules/identity/jobs.py
  - apps/api/aip/modules/identity/step_up.py
  - apps/api/aip/modules/identity/jit.py
  - apps/api/aip/modules/identity/routes.py
  - apps/api/aip/modules/identity/schemas.py
  - apps/api/aip/modules/identity/api.py
  - apps/api/aip/modules/identity/manifest.toml
  - apps/api/aip/modules/identity/tests/
  - infra/keycloak/realm-aip.json (IdP mapper for upstream `amr`; `forwardParameters` on the IdPs)
  - infra/keycloak/realm-mock-idp.json (hard-coded `amr` claim per mock client)
  - infra/keycloak/themes/aip/email/ (theme.properties, messages for the execute-actions email)
  - apps/web/src/features/identity/step-up.ts
  - config/terms/en-AU/identity.json
- **steps**:
  - 1. Alembic revision (raw SQL via `op.execute`, tenant template, FORCE RLS).
    - Table `user_invite`: id, tenant_id, user_id, email citext, user_class, organisation_id NULL, invited_by, method (`local`|`sso`), keycloak_user_id uuid NULL, status (`pending`|`sent`|`accepted`|`revoked`|`failed`), last_error NULL, expires_at (7 days), sent_at, accepted_at, revoked_at, created_at.
    - Add `mfa_enrolled_at timestamptz NULL` to `app_user`. It is set the first time a session with `aal=2` is issued for the user, and ACCESS-05 shows it.
  - 2. Keycloak adapter. Extend `keycloak_admin.py` (IDENTITY-03), through the `aip-admin` service account, with these methods:
    - `create_user(email, *, first_name, last_name, required_actions, attributes) -> UUID`: `create_user({username: email, email, enabled: True, emailVerified: False, requiredActions, attributes:{aip_user_id:[...]}}, exist_ok=False)`. On 409, look the user up with `get_users({'email': email, 'exact': True})` and return the existing id.
    - `send_actions_email(user_id, actions, *, lifespan_s, redirect_uri)`: `send_update_account(..., client_id='aip-api')`.
    - `enable_user(user_id)` and `disable_user(user_id)`.
    - `reset_mfa(user_id)`: delete the user's `otp` and `webauthn` credentials and add the required action `CONFIGURE_TOTP`.
    - Errors become `KeycloakUnavailable` (5xx or timeout) or `KeycloakRejected` (4xx, with the message).
  - 3. Invite. `POST /api/v1/identity/invites {email, userClass:'staff', organisationId?, firstName, lastName}` requires `requires('identity.user.manage')` (ACCESS-01) and `step_up()` (step 6). In one `with_tenant` transaction it does all of the following:
    - Create an `invited` `app_user` and a `member` membership. When the email domain maps to an IdP in `login_directory`, the user is `sso_managed=true` with `method='sso'`. Otherwise the user is local, `identity_register_email` (IDENTITY-02) runs, and `EMAIL_IN_OTHER_TENANT` gives 409.
    - Insert `user_invite` with status `pending`.
    - For `method='local'`, atomically enqueue the Procrastinate job `identity.send_invite` with `{tenant_id, invite_id}`.
    - Write `auth_event` `invite.created`.
    - Return 201 `{inviteId, userId, method}`.
    - For `method='sso'` no Keycloak call or email is made. The brokered Keycloak user appears at first SSO sign-in, and IDENTITY-02's JIT links the invited row. An app-sent notification for SSO invites is a follow-up for the notifications module.
    - Re-inviting the same email revokes the previous pending or sent invite and creates a new one.
    - `create_invite(conn, *, email, user_class, ...)` is exported from `api.py` without the step-up, for TENANCY-05's admin invite.
  - 4. `identity.send_invite` job (idempotent; handler re-enters `with_tenant`):
    - It skips anything that is not `pending` or `sent`.
    - It calls `create_user` with required actions `['VERIFY_EMAIL','UPDATE_PASSWORD','CONFIGURE_TOTP']` and stores `keycloak_user_id` on both `user_invite` and `app_user`.
    - It calls `send_actions_email(..., lifespan_s=604800, redirect_uri=f'{APP_ORIGIN}/login?invited=1')`, so Keycloak sends the email with the `aip` email theme. It then sets status `sent` and `sent_at`.
    - `KeycloakUnavailable` re-raises so Procrastinate retries with backoff (max 5). `KeycloakRejected` sets status `failed` with `last_error` and writes `auth_event` `invite.failed`.
    - Other endpoints, all requiring `identity.user.manage` and `step_up()`:
      - `POST /api/v1/identity/invites/{id}/resend` re-enqueues the job.
      - `DELETE /api/v1/identity/invites/{id}` revokes. It sets status `revoked` and, for a user still `invited`, enqueues `identity.disable_keycloak_user`.
      - `GET /api/v1/identity/invites?status=` lists invites (`identity.user.read`).
  - 5. Accept. The user follows Keycloak's email link, verifies the email, sets a password (Keycloak password policy, IDENTITY-01) and configures TOTP. Keycloak then sends them to `/login?invited=1`, and they sign in through the normal flow. In JIT (IDENTITY-02 rule (a)), when the matched user is `invited` and has a `user_invite` row:
    - Require an invite for them with status `sent` and `expires_at > now()`, otherwise refuse with `INVITE_INVALID`.
    - Set the invite `accepted` and the user `active`, and write `auth_event` `invite.accepted`.
    - A revoked or expired invite stays refused even if the Keycloak account still works.
  - 6. MFA enforcement and step-up in `step_up.py`.
    - **Every login.** After the IDENTITY-01 checks, the session `aal` comes from `derive_aal` (IDENTITY-03).
      - For local accounts the realm flow guarantees `acr='aal2'`.
      - For brokered accounts the upstream IdP's `amr` is imported by an IdP "Attribute Importer" mapper (`sync mode FORCE`) into user attribute `upstream_amr` and emitted by a client mapper as the ID-token claim `upstream_amr`. `derive_aal` treats `mfa`, `otp`, `hwk`, `swk` or `fido` in `upstream_amr` as aal 2, otherwise 1.
      - An aal-1 SSO session may do ordinary work but never a critical action. In `realm-mock-idp.json`, the client behind `kaefer-oidc` adds a hard-coded claim `amr=["pwd","mfa"]` (a customer IdP that enforces MFA) and the client behind `acme-oidc` adds `amr=["pwd"]` (one that does not), so both paths are testable.
    - **`step_up(max_age_min=None)`**, a FastAPI dependency exported from `api.py`. It passes when the session has `aal == 2` and `now - authenticated_at <= max_age_min` (default: the tenant's `tenant_auth_policy.step_up_max_age_min`, 10). Otherwise it returns 401 `{code:'STEP_UP_REQUIRED', stepUpUrl:'/api/v1/auth/step-up/start?returnTo=<path>'}`.
    - **`GET /api/v1/auth/step-up/start?returnTo=`** (authenticated) builds a Keycloak authorize URL like `login/start`, plus:
      - `prompt=login`, `max_age=0`, `acr_values=aal2` and `login_hint`;
      - `kc_idp_hint=<alias>` for SSO users, with the IdPs' `forwardParameters` set to `prompt,max_age` so the customer IdP re-authenticates.
      - The pre-auth cookie records `purpose='step_up'`, the current `session_id` and `started_at`.
    - **The callback**, for `purpose='step_up'`, requires all of the following and then calls `rotate_session(..., aal=2, amr, authenticated_at=auth_time)` (IDENTITY-03) and redirects to `returnTo`:
      - the ID token `sub` equals the session user's `keycloak_user_id`, otherwise 403 `STEP_UP_SUBJECT_MISMATCH`;
      - `auth_time >= started_at`, otherwise 403 `STEP_UP_STALE`;
      - `derive_aal(...) == 2`, otherwise 403 `MFA_NOT_SATISFIED`, and the session is unchanged.
    - **Critical actions** in this task: invite create, resend and revoke, and MFA reset. IDENTITY-05 (SCIM tokens, user deactivation) and IDENTITY-06 (API clients) apply `step_up()` to their admin routes.
  - 7. MFA reset by an admin: `POST /api/v1/identity/users/{id}/reset-mfa` requires `identity.user.manage` and `step_up()`. In one transaction it:
    - enqueues `identity.reset_keycloak_mfa`, which calls `reset_mfa`;
    - calls `revoke_all_for_user(conn, user_id, 'mfa_reset')`;
    - clears `mfa_enrolled_at`;
    - writes `auth_event` `mfa.reset`.
    - An SSO user gets 409 `MFA_MANAGED_BY_IDP`.
  - 8. Web. `step-up.ts` handles 401 `STEP_UP_REQUIRED` from any mutation: it stores the pending form state in `sessionStorage`, then `window.location.assign(stepUpUrl)`. After returning, the page offers to retry the action. The Keycloak pages do all credential entry. `apps/web` has no password, TOTP or WebAuthn UI. Invite-management screens are ACCESS-05's.
- **acceptance**:
  - An admin invites `carol@client.test`. Keycloak sends one email. After she verifies her email, sets a password and configures TOTP, her first sign-in activates her `app_user` and gives a session with `aal=2`.
  - No password hash, TOTP secret, recovery code or WebAuthn credential is stored in the app database. `aip/modules/identity` imports none of `argon2`, `pyotp`, `webauthn`.
  - A critical action is refused with `STEP_UP_REQUIRED` unless the session has `aal=2` and authenticated within the last 10 minutes. After step-up it succeeds, and the session id has rotated.
  - A revoked or expired invite cannot be used to sign in, even if the Keycloak account exists.
  - Invite creation and job enqueue commit together or not at all.
- **tests** (pytest; integration uses testcontainers-python Postgres, Redis and Keycloak with IDENTITY-01's realm, and Mailpit for mail):
  - **unit**:
    - `invite_method('carol@client.test', directory={'kaefer.test': 'kaefer-oidc'})` returns `local`. `invite_method('dan@kaefer.test', ...)` returns `sso`.
    - `step_up` check: `aal=2` with `authenticated_at` 5 minutes ago passes. 11 minutes ago gives `STEP_UP_REQUIRED`. `aal=1` 1 minute ago gives `STEP_UP_REQUIRED`.
    - `derive_aal(acr=None, amr=['pwd'], upstream_amr=['pwd','mfa'])` returns 2. `derive_aal(None, [], upstream_amr=['pwd'])` returns 1.
    - `build_step_up_url(user_with_idp('kaefer-oidc'))` contains `prompt=login`, `max_age=0`, `acr_values=aal2` and `kc_idp_hint=kaefer-oidc`.
    - Step-up callback checks: `sub` mismatch gives `STEP_UP_SUBJECT_MISMATCH`. `auth_time` 1 s before `started_at` gives `STEP_UP_STALE`.
    - The `send_invite` handler with a fake adapter raising `KeycloakRejected('User exists with same username')` sets status `failed` with that `last_error`. Raising `KeycloakUnavailable` re-raises.
  - **integration**:
    - Invite `carol@client.test` with a fresh step-up session. Expected:
      - 201, an `invited` `app_user`, a `pending` invite and 1 queued job.
      - Run the job: the Keycloak user exists with `requiredActions` equal to `['VERIFY_EMAIL','UPDATE_PASSWORD','CONFIGURE_TOTP']` and attribute `aip_user_id`, the invite is `sent`, and Mailpit has 1 message to carol.
      - Running the job again creates no second Keycloak user.
    - Invite in a transaction that then raises. Expected: no `app_user`, no invite and no job.
    - Invite `dan@kaefer.test`. Expected: `method='sso'`, no job, and no Keycloak user.
    - Follow carol's Mailpit link headlessly: verify the email, set password `Correct-Horse-42!`, configure TOTP, then sign in. Expected: `app_user.status='active'`, the invite is `accepted`, the session has `aal=2` and `mfa_enrolled_at` is set.
    - Revoke an invite after it was sent, then sign in with that Keycloak account. Expected: 403 `INVITE_INVALID` and no session. The disable job leaves the Keycloak user with `enabled=false`.
    - `POST /api/v1/identity/invites` with a session authenticated 11 minutes ago. Expected: 401 `STEP_UP_REQUIRED` with `stepUpUrl`.
    - Run step-up headlessly for carol (password + TOTP). Expected: the session id changes, `authenticated_at` is updated, and the retried invite returns 201.
    - Step-up for bob (`acme-oidc`, upstream `amr=['pwd']`). Expected: 403 `MFA_NOT_SATISFIED`, and his session id and `aal=1` are unchanged.
    - Reset carol's MFA. Expected: Keycloak `get_credentials(carol)` has no `otp` credential, `requiredActions` contains `CONFIGURE_TOTP`, and her sessions are revoked. Resetting alice's MFA gives 409 `MFA_MANAGED_BY_IDP`.
    - Invite `carol@client.test` in `tenant-b` while she is local in `kaefer-demo`. Expected: 409 `EMAIL_IN_OTHER_TENANT`.
  - **e2e**:
    - Playwright on compose: alice (tenant admin, SSO) invites `erin@client.test`. Open the Keycloak email from Mailpit, set a password and configure TOTP (the test computes the code from the manual-entry secret on the themed page). Expected: erin lands on home, and the header shows her email.
    - Alice signs in, waits until her session is older than the step-up window (fake clock via `AIP_TEST_CLOCK_OFFSET`), and tries to invite again. Expected: she is sent to the mock IdP, which re-prompts (`prompt=login`). On return, the invite succeeds after the retry prompt.

## Carried forward from IDENTITY-02 (non-blocking)

- Changing a local (`sso_managed=false`) user's email registers the new address through `identity_register_email`, but the old `login_directory` row of kind `email` is not removed (there is no unregister function), so the old address still resolves to the tenant. Add a SECURITY DEFINER `identity_unregister_email` (same tenant-context and local-user checks) in a new revision and call it from the email-change and user-delete paths, with a test that the old address no longer resolves.
