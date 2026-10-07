# 09 — Tablet hand-over signing for client witnesses

Status: proposal for owner decision · 2026-10-07 · Affects ADR 0005, ADR 0010, threat model (Field PIN, Portal, Signing), portal, inspections, signing.

## The ask

> "Our inspector is onsite with his tablet, logged in. The client inspector doesn't have his device. The inspector
> passes his tablet to the client, client selects his name, enters the PIN he chose in his profile, then signs off the ITP."

Short answer: yes, build it. But the client's name + PIN on the Kaefer tablet is **one factor (`aal1`)**, not `aal2`.
The tablet's device key belongs to the Kaefer inspector, not to the client. So the design adds an optional "own factor"
tap for the client, an honest record, and a safe offline mode.

## 1. User journey (gloved, outdoor, patchy signal)

Design rules: tap targets ≥ 64 px, high-contrast "sunlight" theme, no typing apart from the PIN, ≤ 6 taps for the
client, everything works with no signal.

| # | Who | Screen / tap |
|---|---|---|
| 1 | Host | Signs his own part of the ITP step as usual (his device + PIN = `aal2`). |
| 2 | Host | Taps **Hand to client to sign**. Picks the point (e.g. "Hold 4.2 – Flange torque"). Screen: "Hand the tablet over and step back." |
| 3 | Client | Big list of **names only**: the client reps invited to this project who may sign this point type (usually 1–4 people). Taps his name. |
| 4 | Client | **Review screen** (one scroll): what he is signing (§2.4). Buttons: **Accept**, **Accept with comment**, **Reject**. |
| 5 | Client | Statement ("I witnessed … and accept …"), then a **6-digit PIN pad** (large keys, masked, no echo). |
| 6 | Client | If he has an own factor: **Tap your key** (FIDO key on his lanyard, works offline) or **Use my phone** (QR, online only). Otherwise skip. |
| 7 | Client | Optional per tenant: draw signature with finger; front camera takes a photo at confirm. |
| 8 | Client | Done screen: "Signed as Jane Smith (Rio Tinto) · fingerprint 3F9A-21C7 · Hand the tablet back." |
| 9 | Host | Unlocks with his own PIN/biometric. Sees the signature chip with its assurance badge. |

Offline: steps 1–9 are identical on screen. The difference is what happens behind the scenes (§3.5) and the
badge on the chip ("Verifying — will confirm when online" vs "Verified").

## 2. Hand-over mode mechanics

### 2.1 Protecting the host's session
- Starting hand-over **locks the host session**. The app enters a single-purpose route that holds a hand-over token
  scoped to `{signoff_request_id, itp_step_id, content_hash}`, valid 10 min, single use.
- No nav rail, no header menu, no back, no search, no deep links. Hardware back = "Cancel signing?".
- Leaving the app (home button, app switch) or 3 min idle ends hand-over and returns to the **host lock screen**.
  Getting back into anything needs the host's PIN/biometric. Recommend Android screen pinning / iPad Guided Access
  through MDM; the PWA alone cannot stop the home button.
- The client never gets a session. The tablet calls one narrow field-API endpoint (`POST /signoffs/{id}/assisted`)
  that checks a credential and writes an attestation. No portal cookie, no client data beyond this step.
- The step content is frozen when hand-over starts. If the host edits anything, the token is void.

### 2.2 Who is in the name list
- Only portal users in the **host's tenant** (e.g. Rio Tinto reps invited to Kaefer's project) who: are active, have a
  grant for this project and asset subtree, hold the witness/counter-sign right for this point type, and have a
  sign-off PIN enrolled.
- Shows display name + company only. No emails, no search box, no "user not found" probing. The list is synced to the
  tablet for offline use (names, user IDs, public keys of their FIDO keys; **never PIN hashes**).

### 2.3 How the client gets a PIN (beforehand)
- Invite → magic link to the portal (own origin, ADR 0005) → profile → **Field sign-off PIN** (6 digits, no trivial
  PINs) and optionally **Register a key/passkey**. Done once, on the client's own device or a desk PC.
- PIN changes and new keys send an email to the client.
- **Not enrolled yet?** He is not in the list; the host sees "Not set up — record as witnessed" (path D below), which
  emails him a link to confirm later. **Never set a PIN on the host's tablet**: the host would see it, and nothing
  proves who is holding the tablet.

### 2.4 What the client sees before signing
ITP number and revision, step number, point type badge (HOLD / WITNESS), asset/tag and location, acceptance criteria,
the recorded result and readings, evidence thumbnails (tap to enlarge), open NCRs or deviations, the host's signature
chip (name, time, assurance), the consent statement from the statement library, and a short **record fingerprint**
(first 8 hex of the SHA-256 of the canonical step content). The same fingerprint is printed on the receipt and the
PDF, so the client can match them.

### 2.5 Hand-back
After Done, Cancel, Reject, timeout or 3 wrong PINs: "Hand back to <host name>" → host lock screen → host PIN.

## 3. Security and evidence analysis

### 3.1 Does client name + PIN on the host's device meet `aal2`? No.
- ADR 0010 counts "registered company device + PIN" as two factors because **both belong to the same person**: the
  device is enrolled to that worker (R14) and the PIN is his. NIST 800-63B requires each authenticator to be bound to
  and controlled by the subscriber.
- In hand-over the device factor is held by the **counterparty** (the contractor whose work is being accepted). For
  the client it proves nothing about him. It proves where and on which Kaefer tablet the signing happened — useful
  corroboration, not a factor.
- What remains is a memorised secret checked by the server = **`aal1`**. Worse, it is typed on a device the other
  party controls, in front of him. This is exactly the residual risk already in the threat model ("both factors
  held by one other person"), with an incentive added.
- So owner option (a) "name + PIN + registered tablet = `aal2`" is fine **only for workers enrolled on that tablet**,
  never for a third party. Option (b) "step up for hold points" is the right instinct; §5 makes it concrete.

### 3.2 Getting the client to `aal2` on the host's tablet
The client needs a second factor **he** holds: a **FIDO2 security key** (NFC tap on Android; USB-C on iPad) or a
**passkey on his own phone** (QR / hybrid; needs internet). AIP PIN (knowledge) + his key (possession) = `aal2`,
phishing-resistant. The key assertion's challenge is `H(content_hash ‖ nonce)`, so it binds to this exact record.
Do **not** use site access-card UIDs (clonable, not authentication).

### 3.3 Brute force and enumeration
- Online: PIN checked server-side only. 5 wrong tries per client per 15 min, hard lock at 10 (unlock by magic link),
  per-device and per-host limits too, alert to client and host's supervisor (R3 numbers). Odds of a dishonest host
  guessing a 6-digit PIN in 5 tries: 1 in 200,000, and every try is logged against his name.
- Offline: the tablet has **no PIN verifier**, so there is **no offline oracle**. Storing an argon2 hash of a
  6-digit PIN on the tablet would let anyone holding the tablet crack it in hours. Offline PINs are sealed to the
  server (below) and every attempt is counted at sync.
- Enumeration: the list is limited to the project's invited reps (they already know each other); no free-text lookup.

### 3.4 Dishonest host (shoulder-surfing, reuse)
- Risk: host watches the PIN, later "signs" for the client. Controls: (1) every assisted signature sends the client
  an **immediate receipt** (email; on sync if offline) with the fingerprint and a one-click **"This wasn't me"**;
  (2) assisted PIN works only inside a hand-over started by a named host, so a forgery points at that host;
  (3) photo at confirm (tenant option) makes a forgery visible; (4) hold points need the client's own factor or later
  confirmation unless the client agreed otherwise (§5); (5) PIN change prompt after a dispute.
- Residual: a host who memorises the PIN can still forge an `aal1` witness that the client fails to dispute. That is
  why `aal1` is labelled on the record and in the PDF, never shown as equal to `aal2`.

### 3.5 Offline signing and sync
- On confirm, the tablet builds the attestation and **seals the PIN** together with `content_hash`, client user ID,
  device ID, hand-over ID and a nonce to the tenant's server public key (HPKE / libsodium sealed box). The host's app
  cannot read it. If a FIDO key was tapped, the tablet verifies the assertion locally with the cached public key
  (instant feedback) and the server re-verifies on sync.
- On sync: server checks PIN (counts toward lockout), checks key assertion, records **server receipt time beside
  device time** and flags skew (R15), sends the receipt. Wrong PIN → signature `rejected_unverified`, host and
  supervisor alerted, step reverts.
- **Holds offline:** a hold may be released offline only by a client signature with a verified own factor (key tap).
  A sealed PIN alone gives `pending_verification`; the hold stays held unless the tenant enabled "provisional
  release" for that project (flagged on the record, auto-revert + NCR if verification fails).

### 3.6 Tenant boundary
The Rio Tinto rep is a `PortalUser` **inside Kaefer's tenant** (email unique per tenant, ADR 0005/portal data model).
His PIN and keys are per tenant; working with another contractor means a separate account and PIN. All writes run
under `with_tenant` + RLS; the endpoint checks host session, host's assignment to the ITP, and the client's grant.
Nothing from Rio Tinto's own systems is touched. Later, federated Rio SSO could replace the PIN for online use.

### 3.7 Repudiation and the audit record
Each assisted signature stores: `signer_user_id`, `signer_party` (client), `facilitated_by` (host user ID),
`mode=assisted_handover`, `method` (`assisted_pin` | `assisted_pin+security_key` | `phone_passkey`),
`assurance_level`, `decision` + comment, statement text/version, `content_hash`, device ID, hand-over ID,
`authenticated_at` (device), `server_received_at`, skew flag, GPS (if allowed), photo and drawn-signature file IDs,
receipt sent at / to, dispute window end, dispute outcome, and the verification state history. All append-only and
hash-chained (signing module); the PDF shows "Signed by J. Smith (Rio Tinto) on Kaefer tablet T-031, facilitated by
A. Brown, PIN only (`aal1`)".

## 4. Alternatives

| Option | Client experience | Assurance | Offline | Pros | Cons |
|---|---|---|---|---|---|
| **A** Owner's flow as-is (name + PIN on host tablet) | Excellent | `aal1` (not `aal2`) | Only by caching PIN hash = crackable | Simplest, familiar | Mislabels assurance if counted as `aal2`; easy to forge by a watching host; weak in a Rio audit |
| **B** A + strengtheners (server/sealed PIN, lockout, receipt + "This wasn't me", photo, drawn signature, locked kiosk) | Excellent (+1 tap) | `aal1`, well evidenced | Yes, verified at sync | Honest record, deterrence, dispute trail | Still one factor; host can learn the PIN |
| **C** QR on tablet → client signs on **own phone** with passkey | Good if he has a phone | `aal2` (phishing-resistant) | No (phone needs internet) | Strongest, no PIN on host device | Needs a phone and signal; some Rio areas restrict phones |
| **D** Host records "witnessed by" + drawn signature → client confirms in portal later | Good on site, chore later | None on site; `aal2` once confirmed | Yes | Always available, ADR 0010-style fallback | Hold stays held; confirmations get forgotten |
| **E1** One-time code to client's email/SMS, typed on tablet | Fair | PIN + OTP ≈ `aal2` (SMS is "restricted") | No | No hardware | Needs phone + signal, the very things missing |
| **E2** B + **FIDO2 key on lanyard** (tap on tablet) | Excellent (one tap) | `aal2`, phishing-resistant, bound to the record | **Yes**, verified locally and at sync | Works in a dead zone, gloves-friendly, no phone | ~A$60–90 per client rep; iPad needs USB-C key |

Rejected: client passkey on the host's tablet (would sync into the host's Google/Apple account); access-card UID tap.

## 5. Recommendation: "Hand-over signing" = B as the base, E2/C as the step-up, D as the fallback

The flow is the owner's flow (pick name → PIN). The system picks the outcome based on what the client used:

| Client used | Online | Offline | Assurance | Record shows | Hold point |
|---|---|---|---|---|---|
| PIN + own key tap | Verified now | Key verified on tablet, PIN at sync | `aal2` | "PIN + security key, assisted on T-031" | Released |
| Own phone passkey (QR) | Verified now | Not available | `aal2` | "Passkey on own phone" | Released |
| PIN only | Verified now | `pending_verification` until sync | `aal1` | "PIN only, assisted on T-031" + photo/signature | Released **only** if the project minimum for client sign-off is `aal1`; else `pending_client_confirmation` |
| Not enrolled / forgot PIN | Witness note + emailed confirm link | Same, link sent at sync | none until confirmed | "Witnessed, awaiting client confirmation" | Held until client confirms in portal (`aal2`) |

Plain rules: witness points and non-hold sign-offs accept PIN-only. Hold points want the client's own factor, unless
the client organisation has agreed in writing that PIN-only is acceptable on that project (tenant admin records this;
privileged, audited, on the compliance page). Every PIN-only signature triggers a receipt with a dispute link.

Why this holds up: a Rio auditor sees exactly how each signature was made and by whom it was facilitated; nothing
claims more assurance than it has (SOC 2 CC6.1/CC7 evidence; ADR 0010 "always recorded"). The field experience stays
"pick name, PIN, done", plus one tap for clients who carry a key.

**Per-tenant / per-project settings**

| Setting | Default | Range |
|---|---|---|
| Hand-over signing enabled | On | On/off per project |
| Minimum for client hold release | `aal2` | `aal1` (privileged, needs "client agreed" note) / `aal2` |
| Minimum for client witness / other sign-off | `aal1` | `aal1` / `aal2` |
| Offline provisional hold release on PIN-only | Off | On/off per project |
| Photo at confirm / drawn signature | Photo off, signature on | Each on/off |
| Dispute window for receipts | 7 days | 1–30 |
| Hand-over idle timeout | 3 min | 1–10 |
| Scrambled PIN pad | Off | On/off |
| PIN length and lockout | Platform floor (6 digits, 5/10) | Stricter only |

## 6. Proposed changes

**ADR 0010 amendment (add a section "Assisted signing on another person's device")**

> A registered device counts as a factor only for users enrolled on that device. When a person signs on someone
> else's device (assisted hand-over, e.g. a client on a contractor's tablet), the device is recorded as context, not
> as a factor: their PIN alone is `aal1`; PIN plus their own security key, or their own passkey, is `aal2`. Assisted
> PINs are never verified on the device; offline they are sealed to the server and verified on sync, and the
> signature is `pending_verification` until then. Each assisted signature records the facilitating user and sends the
> signer a receipt with a dispute link. For signatures by a client or other external party, the countersign fallback
> is confirmation by that signer (or another authorised rep of the same party) in the portal, never by the contractor.
> The minimum for client hold-point release defaults to `aal2`; lowering it to `aal1` is per project, privileged and
> must note the client's agreement.

Also: add **R18** to the threat model register ("assisted signing on a counterparty device: PIN exposure, forgery by
facilitator, offline verification") and point it at the tasks below.

**Tasks** (no PORTAL/FIELD prefixes exist yet; IDs are suggestions)

- **IDENTITY-08 — Client sign-off credentials and assisted verification** · M · depends IDENTITY-07, IDENTITY-03, portal user model
  - Portal profile: set/change 6-digit sign-off PIN (argon2, trivial-PIN block), register FIDO key/passkey; email on change.
  - `verify_assisted(ctx, signer_id, pin|sealed_pin, assertion, content_hash)` returns `aal1`/`aal2`/`reject`, never treats the host device as the signer's factor.
  - Lockout 5/15 min and hard lock at 10, per signer/device/host; alerts; tests prove no PIN verifier is ever synced to devices.
  - HPKE sealed-PIN format with per-tenant server key; replay rejected by nonce + hand-over ID.
- **APPROVALS-07 — Assisted signature states, client-party fallback, receipts and disputes** · M · depends APPROVALS-02, IDENTITY-08
  - States `pending_verification`, `pending_client_confirmation`, `rejected_unverified`, `disputed`; hold release obeys project minimums.
  - Fallback confirmer must be the same external party; contractor countersign blocked by test.
  - Receipt email with fingerprint and one-click dispute; dispute freezes the record and alerts QA manager.
  - All §3.7 fields stored append-only; PDF and exports show method, facilitator and both times.
- **FIELD-01 — Hand-over mode in the field PWA** · L · depends DESIGN-02, IDENTITY-08, APPROVALS-07, offline sync
  - Locked single-route kiosk; host session locked; leave/idle/timeout returns to host lock screen (Playwright test).
  - Name list limited to eligible, enrolled reps; works offline from synced directory; no PIN hashes on device.
  - Review screen with fingerprint, evidence, statement; ≥ 64 px targets; sunlight theme; WebAuthn NFC/USB key tap with local verification.
  - Offline queue of sealed signatures; status badge updates on sync.
- **TENANCY-0x** add the §5 settings to tenant/project settings (S, depends TENANCY-05).

## 7. Questions for the owner

1. Do Rio Tinto client reps carry a phone on the work front, and would they accept a FIDO key on their lanyard if we
   (or Kaefer) supply it?
2. For **hold points**, is PIN-only acceptable if Rio Tinto agrees in writing for a project, or must it always be the
   client's own key/phone (or later confirmation)?
3. Offline: may a hold be provisionally released on a PIN-only client signature before sync, or must the crew wait?
4. Is a photo of the client at signing acceptable (privacy notice, Rio site camera rules)?
5. Which tablets does Kaefer use (Android with NFC, or iPad), and are they under MDM so we can use kiosk/screen pinning?
