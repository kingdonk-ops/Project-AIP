# Coolify demo (OPS-11)

The M0 walking skeleton on the owner's Coolify server (bytedock.io), **synthetic data only**
(ADR 0007). Real customer data never goes here: the API refuses to start with `AIP_ENV=demo` if any
tenant is marked `is_real_customer`. AWS staging (OPS-07/09/10) comes before any real data.

- Stack: `infra/coolify/docker-compose.coolify.yml` (api, worker, migrator and seed one-shots,
  Postgres 16 + pgvector with a nightly backup, Valkey, Keycloak, Gotenberg, RustFS, Mailpit, web).
- One domain: `web` serves the app, proxies `/api/` to the API and, under `/auth/`, only Keycloak's
  `aip` and `mock-idp` realms and static resources; everything else there (the admin console and
  API, the master realm) answers 404. Upstreams see the real client IP, never a client-supplied
  `X-Forwarded-For`.
- Images: built and pushed to GHCR by `.github/workflows/deploy-coolify.yml` on every push to `main`
  (`aip-api`, `aip-migrator`, `aip-web-demo`, `aip-postgres-demo`, `aip-keycloak-demo`, each tagged
  `main` and the git SHA), which then calls the Coolify deploy webhook. The server only pulls.
- No repository files are bind-mounted: Coolify resolves relative mount paths under the app's own
  directory on the server, not the clone, so they would mount empty (the first deploy failed that
  way). The nginx config, the Postgres bootstrap, the Keycloak realms and theme are built into the
  images (`infra/coolify/images/`). The `db-bootstrap` one-shot applies the roles, their passwords and
  Keycloak's database on every deploy, so changing a database password in Coolify takes effect on
  the next redeploy.

## One-time setup (owner)

1. **Rotate the Coolify API token first.** The current one was pasted into a chat; create a new token
   in Coolify (Keys & Tokens > API tokens, deploy permission only) and revoke the old one.
2. **GHCR access.** The repository is public, so make the five packages public after the first
   workflow run (GitHub > Packages > package settings > visibility), or add a GHCR read token to the
   server in Coolify (Servers > Docker registries).
3. **Create the resource in the Coolify UI** (the API cannot create Docker Compose resources):
   project "Kaefer AIP" > environment > + New Resource > Docker Compose, source: the GitHub App,
   repository `kingdonk-ops/Project-AIP`, branch `main`, compose location
   `/infra/coolify/docker-compose.coolify.yml` (exact path and extension).
4. **Domain**: on the `web` service only, set `https://<demo-host>:8080` (Coolify's
   `docker_compose_domains`, port 8080 is the container port). Coolify issues the certificate.
   Leave every other service without a domain.
5. **HTTPS redirect**: in the resource's proxy settings make sure HTTPS redirect is on. The `web`
   nginx sends HSTS itself (SECURITY-11); confirm with
   `curl -sI https://<demo-host>/ | grep -i strict-transport-security`.
6. **Environment variables**: set every variable in `env.example` (resource > Environment
   Variables). Generate secrets as the file says; `APP_ORIGIN` is `https://<demo-host>` and
   `WEBAUTHN_RP_ID` is `<demo-host>`. Never commit real values.
7. **GitHub secrets** (repository > Settings > Secrets and variables > Actions):
   `COOLIFY_WEBHOOK` (the resource's deploy webhook URL, Webhooks tab) and `COOLIFY_TOKEN` (the new
   API token). Add the repository variable `DEMO_URL` = `https://<demo-host>` to run the smoke test
   after each deploy. SECURITY-11: also `COSIGN_PRIVATE_KEY` and `COSIGN_PASSWORD` (a key pair
   from `cosign generate-key-pair`; keep `cosign.pub` to verify). Without them the deploy fails
   at signing, and the `security` workflow fails on main.
8. Deploy once from the UI, then check: `python3 tools/smoke.py https://<demo-host>`.

## Redeploy

Push to `main`: once the `security` workflow passes for that commit, `deploy-coolify` builds the five
images, Trivy-scans them and makes SBOMs (a fixable HIGH/CRITICAL not in
`config/vuln-exceptions.txt` stops it before anything is pushed), pushes them, signs the pushed
digests with cosign and calls the webhook; the demo is updated within about 15 minutes. Scan
reports, SBOMs, digests and the public key are the run's `demo-image-evidence-<sha>` artifact.
Verify an image with
`cosign verify --key cosign.pub --insecure-ignore-tlog=true ghcr.io/kingdonk-ops/aip-api@sha256:<digest>`.
Manual redeploy: Coolify UI > Deploy, or run the workflow from the Actions tab (from `main`).

## Roll back

Set `AIP_IMAGE_TAG` in Coolify to the git SHA of the last good commit (every image is also tagged
with its SHA) and redeploy. Migrations are forward-only: rolling back the code does not undo a
migration, so roll forward with a fix if a migration was the problem. Set `AIP_IMAGE_TAG=main`
again afterwards.

## Backups and restore

`postgres-backup` writes `aip-<UTC stamp>.dump` and `keycloak-<UTC stamp>.dump` (pg_dump custom
format) to the `postgres-backups` volume once a day at container start time + 24 h and keeps
`BACKUP_RETENTION_DAYS` days. RustFS objects live in the `rustfs-data` volume (synthetic files only).

Restore the app database (Coolify terminal on the `postgres` service, which mounts the backups
read only at `/backups`):

```bash
ls -1t /backups                      # newest first
# stop api and worker in the Coolify UI, then:
pg_restore -U postgres -d aip --clean --if-exists --no-owner --role=aip_owner /backups/aip-<stamp>.dump
```

Restore `keycloak` the same way (`-d keycloak --role=keycloak`). Start api and worker again, then
run the smoke test.

## Sign-in on the demo

The demo uses the fixture tenants and the mock-IdP users `alice@kaefer.test` (kaefer-demo) and
`bob@acme.test` (tenant-b). SECURITY-11 (review 11 H1): the demo Keycloak imports realms with no
users and no client-secret defaults (`infra/keycloak/deployed_realms.py`; the dev realms with their
committed passwords are for local dev and CI only). On every deploy the `mock-idp-users` one-shot
creates alice and bob if missing and sets their passwords from `MOCK_IDP_ALICE_PASSWORD` and
`MOCK_IDP_BOB_PASSWORD`. A missing value fails the deploy, and the committed dev passwords are
refused. The `admin-bootstrap` one-shot (TESTING-09) makes `alice@kaefer.test` the kaefer-demo
`tenant_admin` and `bob@acme.test` the tenant-b `tenant_admin` before their first sign-in, and
(TESTING-12) gives `viewer@kaefer.test` the read-only `auditor` role. The viewer exists in the mock
IdP only when the optional `MOCK_IDP_VIEWER_PASSWORD` is set.

After each deploy the workflow runs the walking-skeleton journey against `DEMO_URL` when the
`coolify-demo` environment has the secrets `E2E_USER_A`, `E2E_PASS_A`, `E2E_USER_B` and
`E2E_PASS_B`; without them the step is skipped with a notice. `E2E_PASS_A`/`E2E_PASS_B` must equal
`MOCK_IDP_ALICE_PASSWORD`/`MOCK_IDP_BOB_PASSWORD`. Each run creates one project in kaefer-demo and
archives it at the end. The viewer's server-403 journey (tagged `@viewer`) also runs when the
secrets `E2E_USER_VIEWER` (`viewer@kaefer.test`) and `E2E_PASS_VIEWER` (equal to
`MOCK_IDP_VIEWER_PASSWORD`) are set; without them it is left out with a notice.

Rotating a demo password: change the Coolify variable and the matching `E2E_PASS_*` secret, then
redeploy (the one-shot sets the new password).

## Known limits

- Coolify's API returns logs for one container of a compose stack only; use the UI's per-container
  log tab for the others.
- There is no API call to delete a volume: a clean slate means removing the volumes in the UI
  (Storages tab).
