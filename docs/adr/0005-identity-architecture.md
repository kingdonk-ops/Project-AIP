# ADR 0005: Keycloak handles all staff sign-in; the backend issues sessions and builds field, portal and SCIM

- **Status:** accepted (owner, 2026-10-07: "Ok to both")
- **Date:** 2026-10-07 (revision 2; the first version built staff passwords and MFA in-app)
- **Affects:** identity, access, portal, offline, tenancy; IDENTITY-*, TENANCY-01, ARCH-04, SECURITY-07, DESIGN-02

## Context

The brief needs SAML SSO, SCIM, enforced MFA, email + password, and magic link or PIN for field workers. The first version
of this ADR used Keycloak only to broker SSO and built passwords, MFA and passkeys in the app. That is a large
security-critical surface for a small team (stack review, risk 3). Keycloak is open source (Apache-2.0, ADR 0009) and
already does these well. Keycloak has no native SCIM 2.0 server.

## Decision

| Account type | Who authenticates | Session |
|---|---|---|
| Staff via company SSO (Kaefer, Rio Tinto) | **Keycloak** brokers SAML/OIDC; IdP chosen by email domain (Keycloak Organizations) | App-issued opaque `__Host-` cookie, `user_session` row in Postgres + Redis cache |
| Staff with email + password | **Keycloak**: password policy, brute-force protection, **MFA enforced** (TOTP or passkey/WebAuthn), reset emails | Same |
| Field worker | **Backend**: device-bound key + PIN (PIN hashed with argon2-cffi), or single-use magic link (POST confirm) | Short shift session; device JWT (ES256) for sync |
| Portal user (client, subcontractor) | **Backend**: magic link on the portal's own origin; passkey to counter-sign | Separate cookie and session store |
| API client | **Backend**: OAuth2 client credentials | ES256 JWT, 15 min |

- **Login flow:** the backend completes the OIDC code flow with authlib (PKCE), then issues its own session cookie.
  Browsers never hold Keycloak tokens. The ID token's `acr`/`amr` claims gate step-up for critical actions
  (hold-point release, signing).
- **Invites:** the backend creates the Keycloak user through the admin API (python-keycloak) with required actions
  (set password, configure OTP). Keycloak sends the email. `app_user` and `tenant_membership` stay in the app.
- **Logout and revocation:** the app session is revoked instantly. Keycloak sessions are ended through the admin API
  (an outbox job).
- **SCIM 2.0 server is built in the backend.** Deprovisioning revokes app sessions, devices, links and clients in one
  transaction, then disables the user in Keycloak. Target ≤ 60 s, tested with the Entra ID and Okta validators.
- **Keycloak operations:** version pinned (26.x), realm config as code, its own database, and a 14-day patch window for
  critical CVEs. On Coolify it runs as a container; on AWS as two ECS tasks.
- **Tenant resolution** happens before login through a non-RLS `login_directory` (email domain or tenant slug). After
  that, everything runs in `with_tenant`.
- **Libraries:** `authlib`, `joserfc`, `python-keycloak`, `argon2-cffi` (field PINs only), `limits`.
  No in-app staff password or MFA code.

## Consequences

- IDENTITY-04 shrinks to invites and MFA enforcement through Keycloak.
- Keycloak login pages need a custom theme (tenant accent, terminology).
- If Keycloak operations exceed about 2 days a month, revisit WorkOS (stack review tripwire).
