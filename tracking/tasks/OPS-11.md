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

## As built (2026-10-13)

- `infra/coolify/docker-compose.coolify.yml`, `nginx.conf`, `env.example`, `README.md`;
  `.github/workflows/deploy-coolify.yml`; `tools/smoke.py`. The stack pulls `aip-api`, `aip-migrator` and
  `aip-web-demo` from GHCR by tag (`main` or a git SHA); nothing is built on the server.
- Deviations: the web image stays on nginx (not Caddy; the existing `apps/web` image and the DESIGN-02 header
  notes are nginx). The migrator keeps its own image (`infra/docker/migrator.Dockerfile`, as in the dev stack and
  CI). Valkey stands in for Redis (STACK-05). Keycloak runs behind `web` under `/auth` on the demo origin
  (`KC_HTTP_RELATIVE_PATH=/auth`), so the demo needs one domain; nginx proxies only the `aip` and `mock-idp`
  realms and static resources there (404 for the admin console and API and the master realm), and passes upstream
  the real client IP (`real_ip_recursive` over private hops) rather than a client-supplied `X-Forwarded-For`.
- Guard: `tenants.is_real_customer` (migration `202610131600`) and `tenancy_has_real_customer()`; with
  `AIP_ENV=demo` the API's start-up raises `RealDataInDemoError` if any live tenant has it set (and fails closed
  without a database). Tested in `tenancy/tests/test_demo_guard_db.py`.
- Banner: the demo web build (`VITE_AIP_DEMO=1`) puts the `shell.demoBanner` text in `index.html`, outside the React
  root, so the smoke test sees it without running scripts.
- Headers (DESIGN-02 carry-forward): CSP with `frame-ancestors 'none'`, `Permissions-Policy`, `Referrer-Policy` and
  `nosniff` in both nginx configs, repeated in every location that sets its own headers (checked by
  `tools/tests/test_coolify.py`); Keycloak's `/auth/` location omits our CSP because Keycloak sends its own. HSTS is
  set at Coolify's Traefik (README step 5).
- Not done here, owner steps (README): rotate the Coolify token, create the compose resource in the Coolify UI (the
  API cannot), set the domain and environment variables, add `COOLIFY_WEBHOOK`/`COOLIFY_TOKEN` secrets and the
  `DEMO_URL` variable, make the GHCR packages public. The acceptance checks that need the live server (redeploy
  within 10 minutes, smoke against the demo URL) run in the workflow once those exist; the local compose
  integration run needs Docker, which this environment does not have.
