# IDENTITY-07 — Sign-off assurance: per-tenant minimum, method recording, step-up and countersign decision

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`identity`](../../docs/blueprint/modules/identity/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | IDENTITY-04 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/identity/README.md`](../../docs/blueprint/modules/identity/README.md)
3. ADRs: [0010](../../docs/adr/0010-signoff-assurance.md) (this task's decision), [0005](../../docs/adr/0005-identity-architecture.md), [0001](../../docs/adr/0001-greenfield-python-backend.md), [0002](../../docs/adr/0002-data-access-and-migrations.md)
4. `tracking/tasks/IDENTITY-04.md`, for the existing `step_up()` dependency and the `aal` it reads.

## Spec

Give every critical action one decision function that says *allow*, *step up* or *needs countersign*. It is based on
how the person proved who they are and on the tenant's minimum for that action. The method used is recorded on every decision.

- **files**:
  - `apps/api/migrations/versions/<timestamp>_identity_signoff_policy.py`: `signoff_policy` (tenant_id, action_code text, min_aal smallint CHECK (min_aal IN (1,2)), step_up_max_age_min smallint CHECK 1–60 DEFAULT 10, updated_by, updated_at; PK (tenant_id, action_code); FORCE RLS, template per ADR 0002).
  - `apps/api/aip/modules/identity/assurance.py`: `Assurance` model and the `derive_assurance(session)` and `check_signoff_assurance(ctx, action_code)` functions.
  - `apps/api/aip/modules/identity/routes.py`: `GET/PUT /api/v1/identity/signoff-policy` (admin).
  - `apps/api/aip/modules/identity/api.py`: exports `check_signoff_assurance`, `Assurance` and `SignoffDecision`.
  - `apps/api/aip/modules/identity/tests/test_assurance.py`, `test_signoff_policy.py`
- **steps**:
  - 1. `derive_assurance(session) -> Assurance(level, method, authenticated_at, device_id)`:
    - Keycloak session with `acr='aal2'` and `amr` containing `hwk`/`webauthn` → (2, `passkey`).
    - `acr='aal2'` with `otp` → (2, `totp`).
    - Brokered session whose imported upstream `amr` shows MFA → (2, `idp_mfa`).
    - Field session from a registered device key plus a verified PIN → (2, `device_pin`).
    - Anything else → (1, `password`).
  - 2. `check_signoff_assurance(ctx, action_code) -> SignoffDecision`:
    - Read `signoff_policy` for (tenant, action). If there is no row, default to min_aal 2 and max_age 10.
    - Return `allow` if level ≥ min and `now - authenticated_at ≤ max_age`.
    - Otherwise return `step_up_required` (with `stepUpUrl` from IDENTITY-04) when the user has *any* aal2 method available (passkey/TOTP enrolled, a registered device, or an IdP that reports MFA).
    - Otherwise return `countersign_required`.
    - Every decision carries the `Assurance` so the caller can store it.
  - 3. Admin API:
    - `PUT` lowering a min to 1 requires `step_up()`, emits `identity.signoff_policy.changed` (outbox → audit) and needs permission `identity.signoff_policy.manage`.
    - Values outside {1,2} or 1–60 return 422.
  - 4. Seed default rows for `kaefer-demo`: `hold_point.release`, `witness.countersign`, `itp.signoff` and `record.seal`, all at min 2 and max_age 10.
- **acceptance**:
  - A passkey session less than 10 minutes old releasing a hold point → `allow`, method `passkey`.
  - A password-only SSO user whose IdP reports no MFA but who has enrolled a Keycloak passkey → `step_up_required`.
  - The same user with no aal2 method at all → `countersign_required`.
  - A field user on a registered device with a verified PIN → `allow`, method `device_pin`, with `device_id` set.
  - Lowering `hold_point.release` to min 1 without step-up → 403 `STEP_UP_REQUIRED`. With step-up → 200 and an audit event.
- **tests**:
  - **unit**: a table-driven test of `derive_assurance` over the 5 session shapes above, and freshness at 9:59 (allow) and 10:01 (step_up_required).
  - **integration** (testcontainers Postgres): policy read under `with_tenant`; tenant-b can't read kaefer-demo's policy (RLS); the default applies when a row is missing.
  - **e2e** (Playwright, with IDENTITY-04 and APPROVALS-02 merged): `alice@kaefer.test` releases a hold point → redirected to the passkey step → returns → the release succeeds and the decision shows "Passkey".

## Added by owner answers (2026-10-10, ADR 0010 addendum)

- Project settings, both default off: `holdpoint_client_pin_only` (with an `agreement_ref` text field recording the written agreement) and `client_signing_photo`. Tenant admins and project managers can change them; every change is audited.
- With `holdpoint_client_pin_only` off, a client hold-point release needs the client's phone: a passkey on the phone, or a QR code that opens the website on the phone to confirm. Physical security keys are not required or assumed.
- Offline release: when the setting is on, `check_signoff_assurance` returns `allow_provisional`; the release is stored as provisional and the server validates it on sync (a rejection reverts it and notifies the inspector and the client). With the setting off, an offline hold-point release by a client is not allowed.
- Nothing may depend on device management (kiosk mode, screen pinning); Kaefer's Android tablets are not managed. People sign in with their own username or email and password on their own tablet.
- Tests: setting off and a PIN-only client signature → `step_up_required`; setting on → `allow`; setting on and offline → `allow_provisional`, then a server rejection on sync reverts the release.
