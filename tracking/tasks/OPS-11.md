# OPS-11 — Coolify demo deployment of the walking skeleton (synthetic data only)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 (M0) |
| Size | M |
| Depends on | DATABASE-08, STACK-05 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0003 (jobs), 0004 (layout), 0007 (M0 deploys to Coolify, synthetic data only), 0009 (licences)
4. If the `coolify-bytedock` skill is available in your session, use it for Coolify API/CLI specifics.

## Spec

Deploy the M0 stack to the owner's Coolify server (**bytedock.io**; owner, 2026-10-07) so the walking skeleton runs somewhere real, without
building the AWS pipeline yet (owner decision 2026-10-07). AWS staging (OPS-07/09/10) comes later, before real data.

- **files**:
  - `infra/coolify/docker-compose.coolify.yml`: derived from `infra/docker-compose.yml` (STACK-05). Services: api, worker, migrator (one-shot), postgres (pgvector pg16), redis, keycloak, gotenberg, rustfs, and web (static Vite build served by Caddy, `/api/*` proxied to api).
  - `infra/coolify/README.md`: one-time server setup, domain/TLS, which env vars to set in Coolify, how to redeploy and roll back.
  - `infra/coolify/env.example`: every variable with a dummy value; no real secrets in the repo.
  - `.github/workflows/deploy-coolify.yml`: on push to `main`, build images, push to GHCR, then call the Coolify deploy webhook (`COOLIFY_WEBHOOK` + `COOLIFY_TOKEN` as GitHub secrets).
  - `tools/smoke.py`: stdlib-only smoke test against a base URL.
- **steps**:
  - 1. Build one `aip/api` image (api + worker + migrator commands) and one `aip/web` image, both tagged by git SHA.
  - 2. The migrator runs `alembic upgrade head` as `aip_owner` before api/worker start (`depends_on: condition: service_completed_successfully`).
  - 3. Set `AIP_ENV=demo`. In `demo`, seeds for `kaefer-demo` and `tenant-b` run, and the app shows a "Demo, synthetic data only" banner.
  - 4. Add a startup guard: if `AIP_ENV=demo` and any tenant row has `is_real_customer=true`, the api refuses to start. Real Kaefer data never lands on Coolify (ADR 0007).
  - 5. Postgres and RustFS use named volumes, with a nightly `pg_dump` to a volume. The README documents restore.
  - 6. Keycloak imports `realm-aip.json` and `realm-mock-idp.json`. The Keycloak admin console is not exposed publicly.
  - 7. `tools/smoke.py https://<demo-domain>` checks `GET /api/v1/health/ready` = 200, that the web root returns HTML with the demo banner, and that `GET /api/v1/me` without a cookie returns 401.
- **acceptance**:
  - A push to `main` redeploys the demo within 10 minutes, with no manual steps beyond the one-time setup.
  - The smoke test passes against the demo URL.
  - The demo shows the synthetic-data banner, and the guard in step 4 is proven by a test.
  - No secret values are committed. `env.example` lists every variable.
- **tests**:
  - **unit**:
    - `tools/smoke.py` exits 1 with a readable message when `/health/ready` returns 503 (tested with a local stub server).
    - Startup guard: `AIP_ENV=demo` plus a seeded real-customer tenant raises `RealDataInDemoError`.
  - **integration**:
    - `docker compose -f infra/coolify/docker-compose.coolify.yml up --wait` locally, then `tools/smoke.py http://localhost` passes.
  - **e2e**:
    - After deploy, TESTING-09's Playwright journey runs against the Coolify URL (`E2E_BASE_URL`) and passes.

## Carried forward from DESIGN-02 security review (non-blocking)

- Coolify serves the `apps/web` nginx image directly, with no CDN in front, and `apps/web/nginx.conf` only sets `X-Content-Type-Options` and `Referrer-Policy`. Add the CSP and `frame-ancestors 'none'` from `apps/web/security-headers.json` (and a `Permissions-Policy`) to nginx, repeating them inside any `location` block that uses `add_header`. HSTS belongs at the TLS terminator (Coolify's proxy or CloudFront); confirm it is on. Without this the demo can be framed (clickjacking) and has no CSP.
