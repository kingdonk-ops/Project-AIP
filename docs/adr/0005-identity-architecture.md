# ADR 0005: Keycloak brokers federation only; the app issues every credential and session

- **Status:** accepted (reconciles "Keycloak self-hosted" with "Build local auth in-app on libraries"); owner to confirm
- **Date:** 2026-10-07
- **Affects:** identity, access, portal, offline, tenancy; TENANCY-01, ARCH-04, SECURITY-07

## Context

Two owner decisions only fit together one way. The identity, access-matrix and portal docs still say
WorkOS. Keycloak has no native SCIM 2.0 server (community extensions only; reviewer confidence about 85%,
to verify against current release notes). TENANCY-01 reads the tenant from a Keycloak claim, which doesn't
work for PIN, portal or API users. See docs/reviews/02-identity-login.md.

## Decision

- **Keycloak = federation broker only.** It handles SAML 2.0 / OIDC to customer IdPs (Kaefer, Rio Tinto), with
  one realm for tenants and one for platform operators. The app consumes it via `openid-client`.
- **The NestJS app issues every session and credential:**

| Account type | Credential | Session |
|---|---|---|
| Staff via SSO | Keycloak-brokered OIDC | Opaque `__Host-` cookie, `user_session` row in Postgres with a Redis cache |
| Staff local | Argon2id password + TOTP / WebAuthn (MFA enforced) | Same |
| Field worker | Device-bound key + PIN, or single-use magic link (POST confirm) | Short shift session; device JWT (ES256) for sync |
| Portal user | Magic link + passkey to counter-sign; separate origin | Separate cookie and session store |
| API client | OAuth2 client credentials | ES256 JWT, 15 min |

- **Tenant resolution happens before login**, using a non-RLS `login_directory` (email domain or tenant slug),
  then everything runs in `withTenant`.
- **SCIM 2.0 server built in NestJS.** Deprovisioning revokes sessions, devices, links and clients in one
  transaction. Target: ≤ 60 s, tested against the Entra ID and Okta validators.
- Libraries: `openid-client` v6, `jose`, `@node-rs/argon2`, `otplib`, `@simplewebauthn/server`,
  `rate-limiter-flexible`, `@keycloak/keycloak-admin-client`.
- Ignore WorkOS references in the module docs.

## Consequences

Browsers never hold JWTs, so revocation is immediate. If the owner drops Keycloak, SAML moves in-app
(`@node-saml/node-saml`) and only the broker layer changes.
