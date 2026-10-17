# OPS-09 — Build once → deploy staging → signed prod promotion + digest rollback
<!-- hand-edited: merged OPS-10 (Part B) per board re-draw 2026-10-17 -->
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07); web delivery per ADR 0026 (2026-10-13) -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | L |
| Depends on | OPS-07, STACK-05 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0004 (`infra/terraform`, `apps/api/Dockerfile`), 0026 (web apps as nginx images behind the ALB), 0001 (Python backend: api and worker share one image), 0002 (migrations run as `aip_owner` over a direct connection: `alembic upgrade head`), 0003 (worker is `python -m aip.worker`), 0007 (M0 exit: the staging URL is live)
4. Only if the step needs it: [`tracking/tasks/OPS-07.md`](OPS-07.md) for the network, data and app baseline this task deploys onto

> This task merges the whole supply-chain path. Part A (was OPS-09) builds once, scans, pushes and deploys to
> staging. Part B (was OPS-10) signs, verifies, promotes to production on approval and rolls back on a failed smoke.
> Part B extends Part A's workflow and scripts, so they are one task.

## Part A — build once, scan, push to ECR, deploy staging, smoke (was OPS-09)

On every merge to main, build the `aip/api` image (used by both the api and worker services) and the `aip/web` image once, scan both, push them by digest to ECR with keyless CI credentials, run Alembic migrations, deploy those exact digests to the staging ECS services, and prove it with a smoke check. Signing, production promotion and rollback are Part B.

- **files**:
  - .github/workflows/build-promote.yml
  - infra/terraform/modules/ecr/main.tf
  - infra/terraform/modules/ci-oidc/main.tf
  - infra/terraform/envs/staging/main.tf (add the two module blocks only)
  - infra/deploy/pyproject.toml (uv project: boto3, httpx, pytest)
  - infra/deploy/render_taskdef.py
  - infra/deploy/run_migrations.py
  - infra/deploy/smoke.py
  - infra/deploy/tests/
- **steps**:
  - 1. OPS-07 is the infra baseline under `infra/terraform` (ADR 0004). If an `infrastructure/` tree exists on main, stop and flag it.
  - 2. Add the ECR module: repositories `aip/api` and `aip/web` (later `aip/sandbox-*` via a list variable) with `image_tag_mutability = "IMMUTABLE"`, scan on push, KMS encryption, and a lifecycle rule that never expires an image deployed in the last 90 days.
  - 3. Add the CI OIDC module: a GitHub OIDC provider and the role `aip-ci-staging`, trusted only for `repo:<org>/<repo>:ref:refs/heads/main` and the `staging` environment. Its policy allows only ECR push for the repos above, `ecs:RegisterTaskDefinition`/`UpdateService`/`DescribeServices`/`RunTask` on the staging cluster, `iam:PassRole` for the task roles, and reading the staging migrator secret. There are no long-lived AWS keys in GitHub.
  - 4. In build-promote.yml, the `build` job runs on push to main. It uses `docker buildx` with a cache to build `apps/api/Dockerfile` once, tags it with `${GITHUB_SHA}`, pushes it, and records the digest as a job output and in a `digests.json` artifact. It builds `apps/web/Dockerfile` the same way into `aip/web`. Every later step references `aip/api@sha256:…` and `aip/web@sha256:…`, never a tag.
  - 5. The `scan` job runs Trivy on both pushed digests and fails on CRITICAL or HIGH findings with a fix available. It uploads SARIF to code scanning. An ignore file is allowed only with an expiry date and a reason.
  - 6. The `deploy-staging` job (GitHub environment `staging`) first runs migrations: `run_migrations.py` starts a one-off ECS task from the image digest with command `alembic upgrade head` (DATABASE-08) as `aip_owner` over a direct connection (credentials from Secrets Manager, not PgBouncer), waits for it, and fails the deploy on a non-zero exit. Then `render_taskdef.py` takes each current task definition (`api`, `worker`, `web`), replaces only the image with its digest and sets `GIT_SHA`, registers it, and updates the three services. The job waits for `services-stable` with a 15-minute timeout.
  - 7. In smoke.py, run against the staging URL with retries for up to 3 minutes. `GET /api/v1/health/ready` must return 200. `GET /api/v1/platform/version` must have `commit` equal to `GITHUB_SHA`. `GET /login` must return 200 with a CSP header. The first two prove the new digest is serving. If TESTING-09 is merged, also run its `@staging` Playwright spec. A smoke failure fails the workflow; rollback is Part B.
  - 8. Gate the workflow: build runs only after the CI workflow (ruff, pyright, pytest unit and integration, Vitest, Playwright e2e) succeeds for the same SHA (`workflow_run`, or `needs` if it is in one file). Use concurrency group `deploy-staging` with no cancellation of an in-progress deploy.
- **acceptance**:
  - A merge to main produces one `aip/api` digest and one `aip/web` digest, each scanned and deployed (api and worker share the first), and reported by `/api/v1/platform/version`.
  - A HIGH vulnerability with a fix available blocks the deploy.
  - A failing migration stops the deploy before any service update.
  - The workflow has no AWS access keys; it assumes the OIDC role. The role cannot be assumed from a pull-request ref.
  - tofu validate, fmt and plan are clean for staging, with no unexpected destroys.
- **tests**:
  - **unit** (pytest in `infra/deploy`):
    - `render_taskdef` with a task definition whose container `api` has image `…/aip/api:old`, and digest `sha256:abc`, returns image `…/aip/api@sha256:abc`, `GIT_SHA` set, and every other field unchanged (deep-equal apart from those two).
    - `smoke` with version `{"commit": "deadbeef"}` and expected `cafef00d` exits 1 with "version mismatch". With matching commits and 200s it exits 0. With the first two attempts returning 503 (httpx `MockTransport`), it still passes within its retry window.
    - The `tflint` and `tofu fmt -check` jobs pass. A policy check (conftest/OPA) rejects an `aws_ecr_repository` with `MUTABLE` tags.
  - **integration**:
    - `act` (or a dry-run job on a branch with the deploy steps stubbed) on a commit with a known-vulnerable base image. Expected: the scan job fails and deploy-staging is skipped.
    - Make the migration task exit 1 on purpose. Expected: deploy-staging fails, and `aws ecs describe-services` shows the previous task definition still primary for api, worker and web.
    - `tofu plan` on envs/staging shows only creates for ECR and OIDC resources.
  - **e2e**:
    - Merge a commit to main. Expected: within 30 minutes the staging `/api/v1/platform/version` returns that commit, and `aws ecr describe-images` shows the deployed digest with the tag equal to the SHA.

### Carried forward from the STACK-05 security review (PR #18, non-blocking)

- Add `cap_drop: [ALL]` to the third-party containers that tolerate it (valkey, gotenberg at least); they already have `no-new-privileges`.
- Prefix compose interpolation variables (e.g. `AIP_DATABASE_URL`) so a developer's exported `DATABASE_URL` cannot silently leak into the stack, or document it in `.env.example`.
- `apps/web/nginx.conf`: repeat `Referrer-Policy` inside `location` blocks that use `add_header` (nginx drops server-level headers there).
- `GET /api/v1/platform/version` is public and opens a Postgres connection per request: cache the postgres value for a short TTL or rate-limit it, and list the version disclosure in the threat model.

## Part B — cosign signing, prod promotion approval, digest rollback (merged from OPS-10)

Finish the supply-chain path. Sign every scanned digest with cosign (keyless, using the GitHub OIDC identity), verify the signature before any deploy, promote the same staging digest to production only after a manual approval, and roll back automatically to the last known-good digest when post-deploy smoke fails.

- **files**:
  - .github/workflows/build-promote.yml
  - infra/deploy/verify-signature.sh
  - infra/deploy/last-good.ts
  - infra/deploy/rollback.ts
  - infra/deploy/tests/
  - infra/terraform/envs/production/main.tf
  - infra/terraform/modules/ci-oidc/main.tf (add the production role)
- **steps**:
  - 1. Add a `sign` job after `scan`: `cosign sign --yes <repo>@<digest>` for each app, keyless through GitHub OIDC and Sigstore. Attach the CycloneDX SBOM from STACK-04 as an attestation (`cosign attest --type cyclonedx`). The job needs `id-token: write`; all others keep it off.
  - 2. In verify-signature.sh, run `cosign verify` with `--certificate-identity-regexp '^https://github.com/<org>/<repo>/.github/workflows/build-promote.yml@refs/heads/main$'` and `--certificate-oidc-issuer https://token.actions.githubusercontent.com`. Every deploy step (staging and production) calls it first and aborts on failure. An unsigned image, or one signed from another workflow or branch, never deploys.
  - 3. In last-good.ts, after a successful staging or production smoke, write the digests to SSM Parameter Store at `/aip/<env>/last-good-digests` as JSON `{api, worker, web, sha, at}`. Before deploy, read the current value as the rollback target.
  - 4. Add a `promote-production` job, `needs: deploy-staging`, using GitHub environment `production` with required reviewers (at least 1, not the commit author) and a branch rule limited to main. It does not build: it downloads `digests.json` from the same run, verifies the signatures, runs migrations against production with the Part A script, deploys by digest and smokes. For the record (SOC 2 change log), it writes a summary to the job summary: approver, digests, SHA and migration list.
  - 5. In rollback.ts, when post-deploy smoke fails in either environment, re-register the task definition pointing at the last-good digests, update the services, wait until they are stable, re-run the smoke, and fail the workflow with "rolled back to <sha>". Migrations are forward-only (ADR 0002), so rollback redeploys code only. Document in the script header that every migration must be backward-compatible with the previous release (expand/contract). Also enable the ECS deployment circuit breaker with `rollback = true` in the service module as a second layer.
  - 6. In envs/production/main.tf, compose the OPS-07 modules for production (ap-southeast-2) with production sizes, deletion protection on RDS, and the ECR repos shared from staging (or replicated). Add the production CI role trusted only for environment `production`. Applying production infra needs the owner's AWS account: make the plan clean and leave the apply as a manual step in the PR.
- **acceptance**:
  - Every deployed digest has a verifiable cosign signature and SBOM attestation from this repository's main-branch workflow.
  - Production receives exactly the digest that passed staging, only after a named reviewer approves. Nothing is rebuilt.
  - A failed smoke after deploy restores the previous digest automatically, and the workflow reports it.
  - The production OIDC role cannot be assumed from the staging environment or from a PR.
- **tests**:
  - **unit**:
    - rollback with last-good `{api:'sha256:aaa'}` and current `sha256:bbb` produces an update with image `…@sha256:aaa`. With no last-good value it exits 1 with "no rollback target" and does not touch the services.
    - last-good writes JSON containing all three digests and the SHA. A missing digest throws before any write.
    - verify-signature.sh with a mocked `cosign` exiting 1 exits 1 and prints the image reference.
  - **integration**:
    - Push a locally built, unsigned image to the staging ECR and dispatch the deploy with it. Expected: the verify step fails and the service keeps its old task definition.
    - In staging, deploy a digest whose `/health/ready` returns 503 (env flag `FORCE_UNREADY=1`). Expected: the smoke fails, rollback runs, the service returns to the last-good digest, and the workflow ends red with "rolled back to <sha>".
    - `tofu plan` for envs/production is clean, and the plan shows RDS `deletion_protection = true`.
  - **e2e**:
    - Merge to main, let staging pass, and have a second team member approve `production`. Expected: production `/api/v1/platform/version` returns the same commit as staging, and `cosign verify` on the production task's image digest succeeds from a laptop.
