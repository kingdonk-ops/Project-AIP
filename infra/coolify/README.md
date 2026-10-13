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
5. **HSTS**: in the resource's proxy settings make sure HTTPS redirect is on and add the Traefik
   label `traefik.http.middlewares.aip-hsts.headers.stsSeconds=31536000` (plus
   `stsIncludeSubdomains=true`) to the `web` router's middlewares. Confirm with
   `curl -sI https://<demo-host>/ | grep -i strict-transport-security`.
6. **Environment variables**: set every variable in `env.example` (resource > Environment
   Variables). Generate secrets as the file says; `APP_ORIGIN` is `https://<demo-host>` and
   `WEBAUTHN_RP_ID` is `<demo-host>`. Never commit real values.
7. **GitHub secrets** (repository > Settings > Secrets and variables > Actions):
   `COOLIFY_WEBHOOK` (the resource's deploy webhook URL, Webhooks tab) and `COOLIFY_TOKEN` (the new
   API token). Add the repository variable `DEMO_URL` = `https://<demo-host>` to run the smoke test
   after each deploy.
8. Deploy once from the UI, then check: `python3 tools/smoke.py https://<demo-host>`.

## Redeploy

Push to `main`: the workflow builds, pushes and calls the webhook; the demo is updated within about
10 minutes. Manual redeploy: Coolify UI > Deploy, or re-run the workflow from the Actions tab.

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

The demo uses the fixture tenants and users from `infra/keycloak` (`alice@kaefer.test` through the
mock IdP, `bob@acme.test`, and the local accounts). Their passwords are in the public repository,
so anyone with the URL can sign in as them: acceptable for synthetic data only, never for real data.
The `admin-bootstrap` one-shot (TESTING-09) makes `alice@kaefer.test` the kaefer-demo
`tenant_admin` and `bob@acme.test` the tenant-b `tenant_admin` before their first sign-in.

After each deploy the workflow runs the walking-skeleton journey against `DEMO_URL` when the
`coolify-demo` environment has the secrets `E2E_USER_A`, `E2E_PASS_A`, `E2E_USER_B` and
`E2E_PASS_B` (the two users above); without them the step is skipped with a notice. Each run
creates one project in kaefer-demo and archives it at the end.

## Known limits

- Coolify's API returns logs for one container of a compose stack only; use the UI's per-container
  log tab for the others.
- There is no API call to delete a volume: a clean slate means removing the volumes in the UI
  (Storages tab).
