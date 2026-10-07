# Identity & login specialist review

Reviewer: identity and login development specialist. Scope: `00-brief`, `01-decisions`, `02-advisor-summaries`,
`05-access-matrix`, `pages-global`, `modules/{identity,access,portal,offline,tenancy}`, and existing tasks
(`TENANCY-01`, `SECURITY-05/07`, `STACK-01/05`). The identity and access modules are P0 but have no tasks yet.

## Verdict

**Feasible, but not ready to build.** The two owner decisions fit together only if each one gets a narrow
meaning. "Identity provider: Keycloak self-hosted" should mean that Keycloak handles **federation** (SAML 2.0/OIDC
to customer IdPs) and the operator realm. "Local authentication: build in-app on libraries" should mean that AIP
owns **every credential it issues** (passwords, MFA, PINs, magic links, API clients) and **every session**.
Read any other way, the decisions overlap: Keycloak has its own password, TOTP and WebAuthn stack, so two
credential stores would compete. The identity module text still describes a WorkOS/FastAPI design, so it must
be rewritten before any IDENTITY task starts. SCIM should be built in NestJS, not added to Keycloak.

## Contradictions and gaps found

| # | Where | Problem | Fix |
|---|---|---|---|
| 1 | `01-decisions` vs `identity/README`, `architecture.md`, `data-model.md`, `05-access-matrix` (Staff SSO row), `routes.md` (SSO page), `portal/README` | All of them still say **WorkOS** (`workos_adapter.py`, `workos_user_id`, `workos_organization_id`, `/webhooks/workos`, "per-customer admin portal") and the README calls Keycloak "superseded". The owner decision says Keycloak. | Add an ADR, then rewrite these as `idp_subject`, `idp_alias`, `keycloak_org_id`, and drop the admin-portal link |
| 2 | Keycloak + "build local auth in-app" | It is not stated which system holds local passwords and MFA. The P0 exit criterion "Keycloak SSO/MFA **and** local email+password+MFA" reads as both. | Keycloak handles federation only. AIP is the credential and session authority (see architecture below) |
| 3 | `TENANCY-01` step 3 | The tenant is taken from "a Keycloak claim mapper" on the token. Under the recommended design, browsers never hold Keycloak tokens, and PIN, portal and API principals never pass through Keycloak. | Amend the step to "the tenant comes from the AIP session or the AIP-issued JWT". Map the Keycloak IdP alias or organisation to the tenant once, at login |
| 4 | Brief requires SCIM, decision is Keycloak | Keycloak has **no native SCIM 2.0 server** (see below). The SCIM design assumes WorkOS Directory Sync webhooks. | Build a SCIM server in-app (IDENTITY-09) |
| 5 | `app_user` "one row per person per tenant" under FORCE RLS | Email-first login and magic-link or PIN lookup run **before** the tenant is known, so RLS hides every row. No pre-tenant lookup is designed. | Add a global `login_identifier` table (email/employee-no hash → tenant_id, user_id), read only through a SECURITY DEFINER function with enumeration-safe responses |
| 6 | `identity/data-model` (`app_user.user_class`) vs `portal/data-model` (`portal_users`, `portal_session`) | There are two user stores and two session models for external users. Deprovisioning "in one transaction" then has to touch both. | Keep one `app_user` (class `portal_client` or `subcontractor`) plus `portal_grant`. Use one `user_session` with an `audience` column (`app`, `portal`, `device`) |
| 7 | `api_key` table and "OAuth client credentials" | There are two machine credential mechanisms with overlapping scope. | Use OAuth client credentials only, issued by AIP. An "API key" is just a client secret, shown once |
| 8 | 15-min JWT + 30-day refresh (accepted feature) vs "revocation within minutes, one transaction" | Browser JWTs stay valid for up to 15 minutes after revocation. | Browsers use opaque server-side session cookies, so revocation is immediate. JWTs are only for API clients and device sync |
| 9 | "MFA enforced" (brief) vs field PIN and portal magic link | A magic link alone is a single factor. Device binding is what makes a PIN count as a second factor, and this is not written down anywhere for auditors. | Define the assurance levels (AAL table below). Portal counter-signers enrol a passkey |
| 10 | SSO "re-checks the assertion carries an MFA claim" | SAML `AuthnContextClassRef` and Entra `amr` are inconsistent between IdPs, and Keycloak brokering does not pass them through by default. | Map them where they exist. Otherwise require AIP-side WebAuthn step-up for privileged roles and for signing |
| 11 | `offline/README`: "PIN policy and offline TTL", "encrypted local store" | A 4–6 digit PIN that protects an offline key on a stolen device can be brute-forced offline. | Use a WebAuthn PRF-derived key where supported, cap offline unlock (e.g. 72 h), use remote wipe and MDM, and record the residual risk |
| 12 | `SECURITY-07` (session policy in `tenant_settings`, Python paths) vs `identity.tenant_auth_policy` | Session and MFA policy is designed twice. | Make `tenant_auth_policy` the single owner and re-scope SECURITY-07 to the IP allow-list only |
| 13 | `TENANCY-03` (project-scoped `user_roles`) vs `access.role_assignment`; `SECURITY-05` vs `access.access_review` | Role assignment and access review each have two owners. | ACCESS owns assignment and review data. SECURITY-05 consumes it. TENANCY-03 keeps only organisations |
| 14 | `identity/architecture.md`, `07-task-conventions` | These still use FastAPI file paths, Alembic and `current_principal()` dependencies, and cite ADR 0002, but `docs/adr/` does not exist. | Regenerate them for NestJS (`apps/api/src/modules/identity/…`) and create `docs/adr/` |
| 15 | Open items | No idle or absolute timeouts per class, no SCIM time target, no Keycloak HA/DB/patching plan, and no operator-realm design. | See questions. Proposed defaults are below |

**Keycloak SCIM claim: confirmed, about 85% confidence.** Up to the Keycloak 26.x line, Keycloak ships
no SCIM 2.0 *server* endpoint that Entra ID or Okta can push to. Community extensions exist: the
Captain-P-Goldfish `scim-for-keycloak` (its licence has changed over time), Metatavu's
`keycloak-scim-server`, and `keycloak-scim` (an outbound SCIM *client*). An upstream design discussion is
ongoing, and experimental work may have landed after my information. Check the current release notes
before committing, but do not plan on it. Even if it existed, SCIM terminating in Keycloak would add a hop:
the user would be deactivated in Keycloak while AIP sessions, devices, links and portal grants stayed live.

## Recommended auth architecture

**Principle:** AIP (NestJS `identity` module) is the only session and token issuer and the system of record
for users, memberships and credentials. Keycloak is an upstream OIDC provider that brokers customer IdPs.
Next.js proxies `/api/*` to NestJS on the same origin, so cookies are first-party
(`__Host-aip_sid`, `Secure`, `HttpOnly`, `SameSite=Lax`). CSRF protection is an Origin check plus a
double-submit token on unsafe methods. Do not use NextAuth/Auth.js.

| Account type | Authenticates with | Who issues the session or token | Session / token format | Assurance / step-up | Default timeouts (idle / absolute) |
|---|---|---|---|---|---|
| Staff SSO (Kaefer, Rio staff) | Customer IdP (Entra, Okta, Google) via SAML 2.0 or OIDC, **brokered by Keycloak** (single `aip` realm, Keycloak Organizations, one IdP per customer, routed by email domain). AIP is an OIDC RP to Keycloak (auth code + PKCE, confidential client) | AIP, after the callback. Keycloak tokens stay server-side and are discarded after linking | Opaque 256-bit session id in a cookie. Row in `user_session` (Postgres = truth) with a Redis cache | AAL2 if the IdP asserts MFA, otherwise AIP WebAuthn step-up for privileged roles. WebAuthn step-up (re-auth < 5 min) for hold-point and sign-off | 30 min / 12 h |
| Staff local (no IdP, break-glass admins) | Email + password (Argon2id) + mandatory TOTP or WebAuthn, recovery codes, HIBP k-anonymity check, lockout | AIP | Same opaque cookie | AAL2. Break-glass accounts need WebAuthn only (phishing-resistant) | 30 min / 12 h |
| Field worker (PIN / magic link) | First use: a supervisor-issued magic link (POST-confirm) **registers the device**. The device generates a non-extractable ECDSA P-256 key (WebCrypto, IndexedDB) and sets a PIN. Later use: PIN + a device-key signature over a server nonce. Lockout after 5 attempts | AIP | Cookie session with `audience=device` bound to `device_id`. Sync calls carry DPoP-style (RFC 9449) proofs signed by the device key | AAL2 as possession of the device key plus knowledge of the PIN. Sign-off attributed to the individual. Quick-switch per user | Auto-lock 5 min / 12 h shift |
| Offline PWA | Local unlock by PIN, or a biometric via WebAuthn **PRF** where available, which unwraps a per-user data key (AES-GCM) for Dexie | No server session offline. Queued ops are stamped with user_id and device_id and signed with the device key | On reconnect: re-authenticate, then push. The server rejects or quarantines ops from users deactivated before the op timestamp and re-checks authorisation per op | Offline unlock allowed up to `offline_session_max` (proposed 72 h). Remote wipe on next contact | Device lock 5 min. Offline max 72 h |
| Portal client / subcontractor | **Separate origin** (`portal.…`), own cookie, CSP and WAF. Magic link (POST-confirm, 15 min, single use, SHA-256 hashed) + optional password, plus a **passkey required for counter-sign and witness**. Later: enterprise client SSO through the same Keycloak broker | AIP (portal BFF on the same NestJS identity service) | Opaque cookie, `audience=portal`. Access limited to `portal_grant` | AAL1 to view, AAL2 (passkey) to sign | 15 min / 8 h |
| API client (SAP/Maximo, BI, agents) | OAuth 2.0 `client_credentials` with a client secret (Argon2id hashed, shown once, expiring) or `private_key_jwt`. mTLS later | AIP `/oauth/token` | ES256 JWT (`jose`), 10-min TTL, `tenant_id`, `client_id`, `scope`, `kid`. JWKS published. Keys in KMS or Secrets Manager, rotated | Cannot sign, approve or administer users. Revoking a client invalidates the jti/client in Redis | Token 10 min. Secret ≤ 12 months |
| Super-admin (operator) | A separate Keycloak realm `operators` with required WebAuthn, on a separate operator console origin | AIP operator session (separate cookie and audience) | Opaque cookie | AAL3-ish (hardware key). JIT, ticketed, tenant-approved elevation | 15 min / 4 h |

**Session store:** `user_session` (tenant_id, user_id, audience, device_id, auth_strength, amr,
issued/last_seen/expires, revoked_at) is the source of truth, so revocation runs in the same transaction as
deprovisioning. Redis (tenant-prefixed key builders from TENANCY-02) caches `sid → principal` for at most
60 s and is deleted through the outbox on revoke. Idle timeouts update `last_seen` in Redis and flush lazily.

**Library choices (Node 22 / NestJS)**

| Need | Library | Notes |
|---|---|---|
| OIDC RP to Keycloak | `openid-client` v6 (panva) | Auth code + PKCE, `nonce`/`state` stored in the pre-auth cookie |
| JWT sign/verify, JWKS | `jose` | API-client tokens and device proofs. Never HS256 |
| Password hashing | `@node-rs/argon2` (or `argon2`) | Argon2id, m=19 MiB, t=2, p=1 (OWASP floor). Rehash on login when params change |
| TOTP | `otplib` | ±1 step window. Store the last used step to block replay. Secret encrypted (tenant-prefixed key) |
| WebAuthn / passkeys | `@simplewebauthn/server` + `@simplewebauthn/browser` | MFA, step-up, portal signers, operator. PRF extension for offline key |
| Breached passwords | HIBP range API via the egress allow-list | k-anonymity, fail open with an audit flag |
| Rate limit / lockout | `rate-limiter-flexible` (Redis) + `@nestjs/throttler` | Per IP, per identifier, per device |
| Keycloak provisioning | `@keycloak/keycloak-admin-client` | Create IdPs, import SAML metadata, logout or disable on deprovision |
| SCIM parsing | `scim2-parse-filter`, `scim-patch` + Zod schemas | Own NestJS controllers |
| Not used | `passport-saml` / `@node-saml/node-saml`, NextAuth | Only needed if the owner drops Keycloak (fallback: `@node-saml/node-saml` in-app) |

Keycloak config is code: realm export or `keycloak-config-cli` in the repo, deployed on ECS with its own RDS
database, at least 2 nodes, and patched monthly. Use custom theme login pages for the broker hop only
(users see the IdP, not Keycloak).

## SCIM and deprovisioning

- **Endpoint:** `https://api.…/scim/v2/{tenantSlug}` in NestJS. Implement `/Users`, `/Groups`,
  `/ServiceProviderConfig`, `/ResourceTypes` and `/Schemas`, with PATCH (Entra-style ops), filter `userName eq`
  and `externalId eq`, and pagination. Auth is a per-tenant bearer token (hashed, rotatable) stored with the
  SSO connection. Rate-limit and audit every call.
- **Users:** create or update `app_user` (`sso_managed=true`, `scim_status`, `externalId`, `idp_subject`).
  Identity attributes are read-only in the UI. JIT linking at first SSO login matches on IdP subject, then
  the verified email in the claimed domain. Never auto-link local accounts silently.
- **Groups:** stored as `scim_group` + members. Mapping to role, team and scope lives in ACCESS (ACCESS-07).
  The mapping **cannot grant privileged permissions** (tenant admin, audit, legal hold). Those need a manual
  grant with approval.
- **Deprovision (`active=false` or DELETE):** one DB transaction sets the user inactive, revokes every
  `user_session`, device, magic link, PIN, portal grant and owned API client, and writes `auth_event` plus
  the outbox `user.deactivated` event. After commit, the outbox purges the Redis cache, calls the Keycloak
  admin API to log out and disable the user (best effort, retried), and the approvals module reassigns
  pending steps. Offline devices are revoked and wiped on next contact.
- **Time target:** proposed ≤ 60 s from SCIM receipt to the last request being refused. IdP push cadence
  (Entra about 40 min, Okta near real-time) is outside our control, so state it in contracts. A
  CI e2e test asserts revocation and an alarm tracks p95.
- **Validate** against the Microsoft Entra SCIM validator and Okta's SCIM test suite before the Kaefer pilot.

## Proposed task breakdown

Same style as the existing tasks. All are P0 unless marked. Each is "extend/harden/port" per the task
conventions; ports cite AIP phases 41/42 (invite, cross-org login) and §38/§47 (permissions, discipline).

| ID | Title | Size | Depends on | Goal |
|---|---|---|---|---|
| IDENTITY-01 | Identity ADR: Keycloak as broker, AIP as session issuer; rewrite module docs | S | STACK-01 | Record the reconciliation, remove WorkOS, amend TENANCY-01 step 3 and SECURITY-07 scope |
| IDENTITY-02 | Identity schema and pre-tenant login lookup | M | DATABASE-03, TENANCY-01 | `app_user`, `tenant_membership`, `tenant_auth_policy`, `auth_event`, and a global `login_identifier` with SECURITY DEFINER lookup |
| IDENTITY-03 | Server-side sessions and principal guard | M | IDENTITY-02, TENANCY-02, ARCH-04 | Opaque `__Host-` cookie, `user_session` + Redis cache, idle/absolute timeouts, revoke, CSRF, AAL in context |
| IDENTITY-04 | Local password sign-in, reset and email-first routing | M | IDENTITY-03 | Argon2id, HIBP, lockout and rate limits, enumeration-safe responses, SSO-managed users blocked from password |
| IDENTITY-05 | MFA: TOTP, WebAuthn, recovery codes and step-up | L | IDENTITY-04 | Enrolment and challenge pages, `/auth/step-up` with max-age, MFA reset by an admin with audit |
| IDENTITY-06 | Keycloak broker realm as code and OIDC sign-in | L | IDENTITY-03, STACK-05 | `openid-client` RP, Organizations with domain routing, JIT linking, MFA-claim mapping, tenant from IdP alias |
| IDENTITY-07 | SSO connection admin via Keycloak admin API | M | IDENTITY-06 | Tenant admin adds SAML/OIDC IdPs, imports metadata, claims domains, test sign-in, enforces SSO |
| IDENTITY-08 | Invitations and accept flow | S | IDENTITY-05 | Invite, accept, set password or SSO, MFA enrolment handoff (port AIP 41) |
| IDENTITY-09 | SCIM 2.0 server: Users and Groups | L | IDENTITY-02, ARCH-05 | Per-tenant bearer token, PATCH and filter support, passes the Entra and Okta validators |
| IDENTITY-10 | Deprovisioning and revocation fan-out | M | IDENTITY-03, IDENTITY-09 | One transaction revokes all credentials, emits `user.deactivated`, Keycloak logout, ≤ 60 s e2e test |
| IDENTITY-11 | OAuth client credentials and JWKS | M | IDENTITY-03, ACCESS-02 | `/oauth/token`, ES256 `jose` tokens, scopes, rotation, secret shown once, per-client audit |
| IDENTITY-12 | Magic links (scanner-safe POST confirm) | M | IDENTITY-03 | 15-min single-use hashed tokens, scope summary page, lockout, shared by field and portal |
| IDENTITY-13 | Device registration, PIN and quick-switch (P2 with offline) | L | IDENTITY-12 | Device key pair, PIN + signed nonce, DPoP-style sync proofs, remote revoke and wipe, PRF offline key |
| IDENTITY-14 | Break-glass, external sponsors and operator realm (P1) | M | IDENTITY-05, IDENTITY-06 | Dual-approved time-boxed elevation, sponsor expiry and re-confirmation, WebAuthn-only operator login |

| ID | Title | Size | Depends on | Goal |
|---|---|---|---|---|
| ACCESS-01 | Permission catalogue from module manifests | M | ARCH-02 | Abilities registered per module with a privileged flag, generated `packages/permissions`, drift check |
| ACCESS-02 | Roles and default role seed | M | ACCESS-01, TERMS-01 | Stable codes for the 13 default roles from `05-access-matrix`, terminology-key names, custom roles |
| ACCESS-03 | Scoped role assignment | M | ACCESS-02, TENANCY-03, IDENTITY-02 | Project, team or asset-subtree scope with a validity window. Takes over `user_roles.project_id` from TENANCY-03 |
| ACCESS-04 | Policy service and guard (deny by default) | L | ACCESS-03, IDENTITY-03 | `can(principal, action, resource)` in-process (CASL-style), `@Requires()` guard, versioned cache, fail closed |
| ACCESS-05 | Scope enforcement in data layer | L | ACCESS-04, DATABASE-04 | Denormalised ltree scope tables, query-filter builder, RLS helpers for team/subtree, move trigger |
| ACCESS-06 | Teams, visibility rules and field masks | L | ACCESS-05, SECURITY-06 | Team membership, per-team module/subtree visibility, party field masking with preview |
| ACCESS-07 | SCIM group mapping without escalation | M | ACCESS-03, IDENTITY-09 | Group → role/team/scope mapping that rejects privileged permissions, joiner/mover/leaver sync |
| ACCESS-08 | Overrides, delegation and privileged-grant approval | M | ACCESS-04, ARCH-05 | Per-user overrides, time-boxed delegation, approval for privileged grants, `access_change_log` to audit |
| ACCESS-09 | Generated permission-matrix and IDOR tests | M | ACCESS-04, DATABASE-07 | One CI test per role × module from the matrix, plus cross-team and unshared-record IDOR cases |
| ACCESS-10 | Effective-access explorer and access-review feed | M | ACCESS-06, SECURITY-05 | Explains why a user can or cannot act, exports the matrix, supplies SECURITY-05 reviews |
| ACCESS-11 | Discipline and method-qualified sign-off (P1) | M | ACCESS-04, eligibility | Sign-off gated on competency certificates, not role names (port §47) |
| ACCESS-12 | Portal and external principals in policy (P2) | M | ACCESS-06, IDENTITY-12 | `portal_grant` evaluated by the same policy service, no inherited visibility, commercial modules hidden |

Critical path: IDENTITY-01 → 02 → 03 → (04 → 05) ∥ 06 → 09 → 10. ACCESS-01 → 02 → 03 → 04 → 05 → 09.
The P0 exit criterion needs IDENTITY-01…10 and ACCESS-01…09.

## Questions for the owner

1. Do you confirm the split: Keycloak = federation broker + operator realm, AIP = all local credentials and
   all sessions? The alternative is to drop Keycloak entirely and do SAML in-app with `@node-saml/node-saml`,
   which means one less service to host and patch, but more SAML edge cases to own.
2. Do you accept SCIM built in NestJS (recommended) rather than a third-party Keycloak SCIM extension?
3. SCIM deprovisioning target: is ≤ 60 s from receipt acceptable as the contractual figure, given that IdP
   push lag is outside our control?
4. Session defaults per class (table above): approve them, or give Kaefer/Rio Tinto requirements?
5. Field users: is PIN + registered device acceptable as MFA for your SOC 2/ISO auditors? What maximum
   offline unlock window (72 h proposed)? Are shared tablets MDM-managed?
6. Portal: must client counter-signers enrol a passkey? Is enterprise SSO for clients such as Rio Tinto
   needed at the first portal release (P2) or later?
7. Machine access: client credentials only (no separate API-key product)? Is mTLS needed for any
   integration at launch?
8. Hosting Keycloak: who owns patching and HA (2+ ECS tasks, own RDS database)? Is FIPS mode expected
   for IRAP later?
9. Login across tenants: can one email belong to more than one tenant (e.g. a consultant working for Kaefer and a
   second customer)? If so, the tenant chooser after email entry is required in P0.
