# ADR 0038: Hardening of deployed environments (dev secrets, deployed realms, API edge, gated deploy)

- **Status:** accepted
- **Date:** 2026-10-18
- **Affects:** security, identity, ops; SECURITY-11 (review 11 H1, M2, M4, M6); ADR 0013, ADR 0026

## Context

The repository is public. Review 11 found that the public Coolify demo imported mock-IdP users whose
passwords are committed (H1), that the realms fall back to public dev client secrets (M4), that
`/api/*` reaches the API past nginx with no body cap or security headers (M2), and that the demo deploy
pushed unscanned, locally signed images on every push to main (M6).

## Decision

1. **Dev secrets are an allowlist.** `aip.platform.dev_secrets` lists every publicly known dev value
   (client secrets, cookie and cursor keys, object store keys, and dev database passwords inside any
   `DATABASE_*_URL`). The API (`create_app`) and the worker refuse to start with any of them unless
   `AIP_ENV` is `development`, `test` or unset (`""`, local runs and the test suite, as in
   `projects.settings`). Every deployed environment sets `AIP_ENV`. `IdentitySettings` uses the same
   allowlist.
2. **Deployed Keycloaks import a derived overlay, not the dev realms.** `infra/keycloak/deployed_realms.py`
   drops every user with `credentials` (service accounts stay) and strips the default from every
   `${*_CLIENT_SECRET:default}`. The Coolify Keycloak image generates it in a build stage, and its
   entrypoint refuses to start when a client secret is unset, empty or a dev value (Keycloak would import
   an unset placeholder as literal text). The dev realms stay as they are for local dev and CI.
3. **Demo users come from secrets at deploy time.** The `mock-idp-users` one-shot (kcadm as the bootstrap
   admin, inside the network) creates `alice@kaefer.test` and `bob@acme.test` if missing and sets their
   passwords from `MOCK_IDP_ALICE_PASSWORD` / `MOCK_IDP_BOB_PASSWORD` (`${VAR:?}`) on every deploy, which
   also replaces the committed passwords on a demo imported before this change. `web` waits for it.
4. **The API owns its edge.** A 1 MiB body cap (413, counted as the body streams, so chunked bodies are
   never buffered whole) and `nosniff`, `X-Frame-Options: DENY`, `frame-ancestors 'none'` and HSTS on
   every response (`aip.platform.http.edge`). Both nginx configs send HSTS themselves, so the demo no
   longer depends on a manual Traefik label.
5. **The demo deploy is gated, scanned and signed.** `deploy-coolify` runs on `workflow_run` after a
   green `security` run for a push to main and builds that commit. All five images are Trivy-scanned and
   SBOM'd before anything is pushed. cosign signs the registry digests (read back with
   `docker buildx imagetools inspect`) with `COSIGN_PRIVATE_KEY` and verifies them. A missing key fails
   the deploy, and `security` on main fails too; pull requests keep the ephemeral key. Every action in the
   deploy workflow is SHA-pinned.

## Consequences

- No demo deploy and no green `security` run on main until the owner adds `COSIGN_PRIVATE_KEY` and
  `COSIGN_PASSWORD`, and no demo deploy until Coolify has `MOCK_IDP_ALICE_PASSWORD` /
  `MOCK_IDP_BOB_PASSWORD` (and `E2E_PASS_A/B` match them).
- A base-image CVE now blocks the demo. The Postgres image applies Debian updates and drops `gosu`. The
  Keycloak 26.7.5 base has four fixable findings (pcre2 in UBI micro, the unused mssql-jdbc driver) with
  exceptions expiring 2026-12-01: bump Keycloak rather than renew them.
- A new dev default anywhere must be added to `DEV_SECRETS` (API) or the entrypoint's list (Keycloak);
  `test_coolify.py` cross-checks the realm defaults against the entrypoint.
