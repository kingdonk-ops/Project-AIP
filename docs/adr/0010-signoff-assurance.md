# ADR 0010: Sign-off assurance: one quick check at the moment of signing, per-tenant minimum, countersign fallback

- **Status:** accepted (owner, 2026-10-07: "Yes")
- **Date:** 2026-10-07
- **Affects:** identity, approvals, signing, inspections, offline; IDENTITY-04, IDENTITY-07, APPROVALS-02, ACCESS-05

## Context

Releasing a hold point, signing an ITP step and similar actions create legal and quality records that clients
(e.g. Rio Tinto), auditors (SOC 2) and disputes will rely on. A password alone is weak evidence, because passwords
get shared on site. Forcing authenticator-app codes at every login is a burden for field crews, and some customer
SSO systems don't report whether MFA was used.

## Decision

- **Normal login stays light.** Extra proof is asked for only at the moment of a *critical action* (hold-point
  release, witness/counter-sign, ITP sign-off, record seal). The workflow definition marks which transitions are critical.
- **Any one of these satisfies the check (assurance level `aal2`):**
  - **Passkey / device biometrics** (fingerprint, face) via Keycloak WebAuthn. This is the preferred method.
  - **Registered company device + PIN.** The field-device key plus the PIN (ADR 0005) counts as two factors and works offline.
  - **Authenticator code (TOTP)** via Keycloak.
  - **Company SSO that reports MFA** (IdP `amr`/`acr`).
- **SSO users whose IdP doesn't report MFA** get one Keycloak step at signing time (passkey or code, enrolled once).
- **Per-tenant minimum.** A tenant admin sets the minimum per critical action: `aal2` (default) or `aal1`. Setting
  `aal1` is a privileged change. It needs step-up, is audit-logged and is shown on the tenant's compliance page.
  The setting can't go below `aal1`, so an anonymous or shared credential is never enough.
- **Countersign fallback.** If the signer can't meet the minimum, the action is recorded as `pending_countersign`.
  It doesn't take effect (a hold stays held) until a supervisor with the required assurance and permission
  countersigns. Both people and both assurance levels are on the record.
- **Always recorded.** Every signature and decision stores `assurance_level`, `method` (`passkey` | `device_pin` |
  `totp` | `idp_mfa` | `password`), `authenticated_at` and the device ID if one was used. Reports and exports show it.
- **Freshness:** a step-up is valid for 10 minutes by default (tenant-configurable, 1–60 minutes).

## Consequences

- IDENTITY-07 implements `check_signoff_assurance(ctx, action_code)`, which returns `allow`, `step_up_required` or
  `countersign_required`. APPROVALS-02 calls it instead of a hard-coded MFA check.
- Answers OPEN-QUESTIONS: field-PIN users *can* sign on a registered device, and SSO users without IdP MFA get a
  Keycloak step at signing.

## Owner answers (2026-10-10)

- **One tablet per worker.** People sign in with their username or email and password; tablets are not shared. A
  different person on the same tablet logs out and in again. The field PIN stays a quick re-check at signing
  (`aal1`), not a way to share a login. Sessions lock after a short idle period.
- **Client representatives carry their own phones and will not use physical security keys.** The second factor for
  a hold point is the client's own phone: a passkey on the phone, or a QR code that opens the website on the phone to
  confirm. Later confirmation in the portal stays available.
- **Project setting `holdpoint_client_pin_only`** (default off, with a field for the reference to the written
  agreement). When on, a client PIN alone releases a hold point. When off, a hold point needs the phone or website
  confirmation, or later confirmation.
- **Offline.** A hold point may be released provisionally on a PIN-only client signature before sync, only where the
  project setting allows PIN-only. The release is marked provisional until the server validates it on sync; a
  rejection reverts it and notifies the inspector and the client.
- **Photo of the client at signing** is an optional tenant or project setting, default off.
- **Devices.** Kaefer uses Android tablets with NFC and no MDM. Nothing may depend on MDM features such as kiosk
  mode or screen pinning; auto-lock, short sessions and logout are enforced in the app.
- Client reviewer permissions (sign-off of hold points, witness points and reports) are role permissions that the
  tenant admin can change (ACCESS-02).

## Owner answers, part 2 (2026-10-10)

- **Clients sign in to the client portal** with their own username and password (and the second step that local accounts
  already require, ADR 0005) and sign off there: hold points, witness points and reports. This is the normal route.
  Signing on the inspector's tablet with a PIN stays an optional route controlled by the project setting above.
- **Later:** a dedicated client app for ITP sign-off, scheduling and report coding (backlog; the portal is the first
  version of it).
- **Offline grace for permission changes.** The owner wants queued offline drafts to keep their signing authority until
  they sync. That is accepted with limits: the grace covers only role-permission edits made after the device's last
  sync, and only within the maximum offline period (OPEN-QUESTIONS 7). It never covers a deactivated user, a revoked
  session or a removed device. The device records the access version it last synced with, and the server checks that
  version when the draft arrives; anything outside the limits is held for review or countersign.

