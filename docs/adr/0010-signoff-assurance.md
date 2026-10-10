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
  sync, and only within the offline signing limits in part 3. It never covers a deactivated user, a revoked
  session or a removed device. The device records the access version it last synced with, and the server checks that
  version when the draft arrives; anything outside the limits is held for review or countersign.

## Owner answers, part 3: offline timers (2026-10-10, revised the same day)

The first version of this part used one 72-hour ceiling and a 4-hour reconcile deadline. The owner replaced it: calendar
time penalises people who are simply off shift (long weekends, rostered days off, FIFO travel), so two separate clocks
are used. All thresholds are platform defaults; a tenant admin may shorten them, never lengthen them.

- **Track A, idle device (nothing unsynced).** Cached drawings, checklists and forms stay usable for **14 days** since the
  last contact with the server. After that the app asks for one reconnect to re-validate the session. There is no admin
  lockout.
- **Track B, unsynced provisional records.** Inspectors may record and provisionally sign hold points and witness points
  offline so blasting, coating and erection crews are not stopped; such records carry `PROVISIONAL_OFFLINE`. The clock starts
  at the oldest pending record:
  - 0 to 72 hours: normal work.
  - 72 to 120 hours: a banner ("3 signed records pending sync. Connect within 48 hours"); work continues.
  - 120 hours: new provisional sign-offs are blocked until the queue syncs. Pending records stay in the encrypted local
    store and are never deleted.
- **On reconnect** the app starts syncing by itself and sends small payloads first (sign-off records with their attachment
  hashes, statuses), then photos and video in a deferred queue. There is no fixed 4-hour deadline, because a flickering
  signal would cause false failures. New provisional sign-offs are blocked only if sync has not completed 24 hours after the
  device first regained connectivity.
- **Session interlock.** While provisional records older than 72 hours are pending, the user cannot log out or switch user
  until the queue is empty. A tenant admin can override with an audit entry (a stuck record, a handed-in device). Logging
  out never deletes pending records.
- **Only signing is gated.** Read-only access to drawings and specifications already on the device is never locked, even
  after a timeout, for safety on site.
- Offline device caches are purged automatically once the server acknowledges reconciliation, and at most 30 days after.
- The device time is informational. The server records when it received each record, the device, the device's last sync
  and its access version, rejects a device time later than the receive time, and flags large differences for review.

### Adjustments proposed (owner to confirm)

1. **Signing authority needs a recent online check.** New provisional sign-offs also require an online validation no
   older than 7 days; Track A's 14 days covers reading cached material only. Otherwise a user deactivated or stripped of a
   permission while their tablet sat idle could still sign on day 13 and then get a further 120 hours.
2. **Unmanaged tablets cannot be wiped remotely.** The local store is encrypted with a key that needs the user's unlock, the
   app locks after a short idle period, and on the next contact a deactivated user's or revoked device's cache is wiped.
   Rio Tinto may require shorter limits; check the contract.
3. **Sign-offs before their photos.** The server accepts a sign-off with its attachment hashes marked "evidence pending";
   the sealed report cannot be finalised until every attachment arrives.
4. **This is a web app, not a native one.** Browsers can evict local storage under pressure, so the app must request
   persistent storage, be installed to the home screen and show storage status; background sync is not guaranteed, so sync
   also runs on app open and when the browser reports it is online. The Android callbacks in the owner's note
   (connectivity broadcasts, WorkManager) apply to a native app and are not available here.
5. The permission grace in part 2 is bounded by Track B and by adjustment 1.
