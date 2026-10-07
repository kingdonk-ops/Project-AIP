# IDENTITY-04 — Invite/accept, local Argon2id password + TOTP/WebAuthn MFA

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

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
3. ADRs: [0005](../../docs/adr/0005-identity-architecture.md) (library list), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. Only if the step needs it: [`data-model.md`](../../docs/blueprint/modules/identity/data-model.md) (tables `user_invite`, `mfa_credential`), [`docs/reviews/02-identity-login.md`](../../docs/reviews/02-identity-login.md) (library table)

## Spec

Let non-SSO customers join by invitation and sign in with an Argon2id password plus mandatory TOTP or WebAuthn, with enumeration-safe responses and lockout.

- **files**:
  - db/migrations/<timestamp>_identity_invites_mfa.sql
  - apps/api/src/modules/identity/invites/invites.service.ts
  - apps/api/src/modules/identity/invites/invites.controller.ts
  - apps/api/src/modules/identity/invites/invite-mailer.ts
  - apps/api/src/modules/identity/local/password.service.ts
  - apps/api/src/modules/identity/local/password-login.controller.ts
  - apps/api/src/modules/identity/mfa/totp.service.ts
  - apps/api/src/modules/identity/mfa/webauthn.service.ts
  - apps/api/src/modules/identity/mfa/recovery-codes.ts
  - apps/api/src/modules/identity/mfa/mfa.controller.ts
  - apps/web/src/features/identity/AcceptInvitePage.tsx
  - apps/web/src/features/identity/PasswordSignIn.tsx
  - apps/web/src/features/identity/MfaChallengePage.tsx
  - apps/web/src/features/identity/MfaEnrolPage.tsx
  - apps/api/src/modules/identity/tests/local/
- **steps**:
  - 1. Migration (tenant template, FORCE RLS). Table `user_invite`: id, tenant_id, email citext, user_class, organisation_id NULL, invited_by, token_hash bytea UNIQUE, expires_at (7 days), accepted_at, revoked_at, created_at. Table `mfa_credential`: id, tenant_id, user_id, kind (`totp`|`webauthn`|`recovery_code`), secret_enc bytea (TOTP secret, AES-256-GCM with `MFA_SECRET_KEY` until the per-tenant keys of ADR 0006 exist), last_used_step bigint, credential_id bytea, public_key bytea, sign_count bigint, transports text[], code_hash text, used_at, label, created_at, deleted_at. Add `password_changed_at` to `app_user`.
  - 2. Invites. `POST /api/v1/identity/invites {email, userClass, organisationId?}` requires `@Requires('identity.user.manage')` (ACCESS-01). It creates an `invited` `app_user` and membership, a 32-byte random token stored as SHA-256, and sends `${APP_ORIGIN}/invite/<token>` through the `InviteMailer` port (SMTP adapter selected by the STACK-02 capability factory; in-memory adapter in tests, readable at `GET /api/v1/_test/mailbox` only when `NODE_ENV=test`). Re-inviting revokes the previous pending invite. For an email in a domain with `sso_enforced`, the user is created `sso_managed=true` and the email says to sign in with the company account.
  - 3. Accept. `GET /api/v1/auth/invites/:token` returns `{tenantName, email, method:'password'|'sso'}`, or 404 `INVITE_INVALID` if the invite is expired, used or revoked. `POST /api/v1/auth/invites/:token/accept {password}`: the password must be 12 to 128 characters and not in HIBP (k-anonymity range API, 2 s timeout; on failure, accept and record `auth_event.detail.hibp='unavailable'`). Hash with `@node-rs/argon2` Argon2id (m=19456 KiB, t=2, p=1). Mark the invite accepted, set the user active, and issue an `aal=1` session flagged `mfa_enrolment_required`. While the flag is set, every route except `/me`, the MFA enrolment endpoints and logout returns 403 `MFA_ENROLMENT_REQUIRED`.
  - 4. MFA enrolment. TOTP uses `otplib` (SHA-1, 30 s, 6 digits, window ±1), with the secret encrypted and an otpauth URI for a QR code; it is confirmed with a code. WebAuthn uses `@simplewebauthn/server` (rpID = the APP_ORIGIN host, challenge held server-side for 5 minutes). After the first factor is enrolled, generate 10 recovery codes (shown once, Argon2id-hashed, single use), then `rotateSession` to `aal=2`.
  - 5. Password login. `POST /api/v1/auth/password {email, password, tenantSlug?}`. Find candidate tenants through `identity_resolve_login('email', ...)` and verify the password per tenant. Unknown email, wrong password, an `sso_managed` user and a deactivated user all return the same 401 `INVALID_CREDENTIALS`; the unknown path runs a dummy Argon2 verify to equalise timing, and `auth_event` records the real reason. Lockout with `rate-limiter-flexible` in Redis: 5 failures per identifier per 15 minutes, also for nonexistent identifiers, and 50 per IP per 15 minutes, giving 429 `TOO_MANY_ATTEMPTS`. If the stored hash uses old parameters, rehash on success. If the password is valid in more than one tenant, return 200 `{chooseTenant:[{slug,name}]}` and the client resubmits with `tenantSlug`. On success, set a sealed 5-minute `__Host-aip_mfa` cookie but no session.
  - 6. `POST /api/v1/auth/mfa/verify {totp | webauthnAssertion | recoveryCode}` checks the `__Host-aip_mfa` cookie, verifies the factor and issues the session with `aal=2` and `amr` `['pwd','otp'|'hwk'|'rec']`. A TOTP step at or below `last_used_step` is rejected as a replay.
  - 7. Web pages: `/invite/[token]`; the password branch of the `/login` email-first form (`login/start` returned `method:'password'`); `/login/mfa`; and `/settings/profile/security` for enrolment and regenerating recovery codes. Password reset and admin MFA reset are out of scope (follow-up tasks).
- **acceptance**:
  - An invited local user can accept, set a password, enrol TOTP or a passkey and sign in. No session exists before the second factor passes.
  - SSO-managed users can never sign in with a password.
  - Unknown email and wrong password are indistinguishable by status, body and timing class.
  - Secrets, tokens and recovery codes are stored only hashed or encrypted.
- **tests**:
  - **unit**:
    - `hashPassword('correct horse battery staple')` starts with `$argon2id$v=19$m=19456,t=2,p=1$`.
    - `validatePassword('short')` returns `TOO_SHORT`. `validatePassword('P@ssw0rd1234')` with a HIBP stub count of 5 returns `BREACHED`. With the HIBP stub timing out, it returns ok with `hibpUnavailable: true`.
    - TOTP verification for step s when `last_used_step = s` returns `REPLAY`. Step s+1 is ok. Step s-2 is invalid.
    - `needsRehash('$argon2id$v=19$m=4096,t=3,p=1$...')` returns true.
  - **integration**:
    - Invite `carol@client.test`. Expected: an `invited` app_user, and `token_hash` equals SHA-256 of the token in the captured mail. Accept with a valid password. Expected: status `active`. Accept again. Expected: 404 `INVITE_INVALID`.
    - An invite with `expires_at` in the past. Expected: 404 `INVITE_INVALID`.
    - Six wrong passwords for carol. Expected: the 6th returns 429. An unknown email also returns 429 after 5 attempts.
    - Unknown email versus wrong password, 20 tries each. Expected: identical status and body, and a p50 latency difference under 50 ms.
    - Password login for SSO-managed alice. Expected: 401 `INVALID_CREDENTIALS` and an `auth_event` with reason `sso_managed`.
    - A correct password without MFA verification, then `GET /api/v1/me`. Expected: 401.
    - After accepting with no factor enrolled: `GET /api/v1/projects` returns 403 `MFA_ENROLMENT_REQUIRED` and `GET /me` returns 200.
    - WebAuthn with a software authenticator: register, then authenticate. Expected: a session with `aal=2` and `amr` containing `hwk`.
  - **e2e**:
    - Playwright: a tenant admin invites `dave@local.test`. Open the link from the test mailbox, set a password, enrol TOTP (the test computes the code from the manual-entry secret shown on the page) and save the recovery codes. Expected: land on home. Sign out, then sign in with password + TOTP. Expected: home. Sign in with a recovery code. Expected: it works once and fails on second use.
