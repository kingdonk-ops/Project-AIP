# OPS-09 — Build once, scan, push to ECR, deploy staging, smoke
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-07, STACK-05 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0004 (`infra/terraform`, `apps/api/Dockerfile`, SPAs on S3 + CloudFront), 0001 (Python backend: api and worker share one image), 0002 (migrations run as `aip_owner` over a direct connection: `alembic upgrade head`), 0003 (worker is `python -m aip.worker`), 0007 (M0 exit: the staging URL is live)
4. Only if the step needs it: [`tracking/tasks/OPS-07.md`](OPS-07.md) for the network, data and app baseline this task deploys onto

## Spec

On every merge to main, build the `aip/api` image (used by both the api and worker services) and the web SPA bundle once, scan the image, push it by digest to ECR with keyless CI credentials, run Alembic migrations, deploy that exact digest to the staging ECS services and the bundle to the staging web bucket, and prove it with a smoke check. Signing, production promotion and rollback are OPS-10.

- **files**:
  - .github/workflows/build-promote.yml
  - infra/terraform/modules/ecr/main.tf
  - infra/terraform/modules/ci-oidc/main.tf
  - infra/terraform/envs/staging/main.tf (add the two module blocks only)
  - infra/deploy/pyproject.toml (uv project: boto3, httpx, pytest)
  - infra/deploy/render_taskdef.py
  - infra/deploy/run_migrations.py
  - infra/deploy/publish_web.py
  - infra/deploy/smoke.py
  - infra/deploy/tests/
- **steps**:
  - 1. OPS-07 is the infra baseline under `infra/terraform` (ADR 0004). If an `infrastructure/` tree exists on main, stop and flag it.
  - 2. Add the ECR module: repository `aip/api` (later `aip/sandbox-*` via a list variable) with `image_tag_mutability = "IMMUTABLE"`, scan on push, KMS encryption, and a lifecycle rule that never expires an image deployed in the last 90 days.
  - 3. Add the CI OIDC module: a GitHub OIDC provider and the role `aip-ci-staging`, trusted only for `repo:<org>/<repo>:ref:refs/heads/main` and the `staging` environment. Its policy allows only ECR push for the repos above, `ecs:RegisterTaskDefinition`/`UpdateService`/`DescribeServices`/`RunTask` on the staging cluster, `iam:PassRole` for the task roles, `s3:PutObject`/`ListBucket` on the staging web bucket, `cloudfront:CreateInvalidation` on the staging distribution, and reading the staging migrator secret. There are no long-lived AWS keys in GitHub.
  - 4. In build-promote.yml, the `build` job runs on push to main. It uses `docker buildx` with a cache to build `apps/api/Dockerfile` once, tags it with `${GITHUB_SHA}`, pushes it, and records the digest as a job output and in a `digests.json` artifact. It also runs `pnpm --filter web build` once and uploads `web-dist-${GITHUB_SHA}` as an artifact. Every later step references `aip/api@sha256:…`, never a tag.
  - 5. The `scan` job runs Trivy on the pushed digest and fails on CRITICAL or HIGH findings with a fix available. It uploads SARIF to code scanning. An ignore file is allowed only with an expiry date and a reason.
  - 6. The `deploy-staging` job (GitHub environment `staging`) first runs migrations: `run_migrations.py` starts a one-off ECS task from the image digest with command `alembic upgrade head` (DATABASE-08) as `aip_owner` over a direct connection (credentials from Secrets Manager, not PgBouncer), waits for it, and fails the deploy on a non-zero exit. Then `render_taskdef.py` takes each current task definition (`api`, `worker`), replaces only the image with the digest and sets `GIT_SHA`, registers it, and updates both services. `publish_web.py` syncs the bundle to `s3://<web-bucket>/releases/<sha>/`, switches the CloudFront origin path (or `current/` prefix) to it and invalidates `/index.html`. The job waits for `services-stable` with a 15-minute timeout.
  - 7. In smoke.py, run against the staging URL with retries for up to 3 minutes. `GET /api/v1/health/ready` must return 200. `GET /api/v1/platform/version` must have `commit` equal to `GITHUB_SHA`. `GET /login` must return 200 with a CSP header. The first two prove the new digest is serving. If TESTING-09 is merged, also run its `@staging` Playwright spec. A smoke failure fails the workflow; rollback is OPS-10.
  - 8. Gate the workflow: build runs only after the CI workflow (ruff, pyright, pytest unit and integration, Vitest, Playwright e2e) succeeds for the same SHA (`workflow_run`, or `needs` if it is in one file). Use concurrency group `deploy-staging` with no cancellation of an in-progress deploy.
- **acceptance**:
  - A merge to main produces one image digest and one web bundle, and the same digest is scanned, deployed to api and worker, and reported by `/api/v1/platform/version`.
  - A HIGH vulnerability with a fix available blocks the deploy.
  - A failing migration stops the deploy before any service update or web publish.
  - The workflow has no AWS access keys; it assumes the OIDC role. The role cannot be assumed from a pull-request ref.
  - tofu validate, fmt and plan are clean for staging, with no unexpected destroys.
- **tests**:
  - **unit** (pytest in `infra/deploy`):
    - `render_taskdef` with a task definition whose container `api` has image `…/aip/api:old`, and digest `sha256:abc`, returns image `…/aip/api@sha256:abc`, `GIT_SHA` set, and every other field unchanged (deep-equal apart from those two).
    - `smoke` with version `{"commit": "deadbeef"}` and expected `cafef00d` exits 1 with "version mismatch". With matching commits and 200s it exits 0. With the first two attempts returning 503 (httpx `MockTransport`), it still passes within its retry window.
    - The `tflint` and `tofu fmt -check` jobs pass. A policy check (conftest/OPA) rejects an `aws_ecr_repository` with `MUTABLE` tags.
  - **integration**:
    - `act` (or a dry-run job on a branch with the deploy steps stubbed) on a commit with a known-vulnerable base image. Expected: the scan job fails and deploy-staging is skipped.
    - Make the migration task exit 1 on purpose. Expected: deploy-staging fails, and `aws ecs describe-services` shows the previous task definition still primary for api and worker, and the web bundle prefix is unchanged.
    - `tofu plan` on envs/staging shows only creates for ECR and OIDC resources.
  - **e2e**:
    - Merge a commit to main. Expected: within 30 minutes the staging `/api/v1/platform/version` returns that commit, and `aws ecr describe-images` shows the deployed digest with the tag equal to the SHA.

## Carried forward from the STACK-05 security review (PR #18, non-blocking)

- Add `cap_drop: [ALL]` to the third-party containers that tolerate it (valkey, gotenberg at least); they already have `no-new-privileges`.
- Prefix compose interpolation variables (e.g. `AIP_DATABASE_URL`) so a developer's exported `DATABASE_URL` cannot silently leak into the stack, or document it in `.env.example`.
- `apps/web/nginx.conf`: repeat `Referrer-Policy` inside `location` blocks that use `add_header` (nginx drops server-level headers there).
- `GET /api/v1/platform/version` is public and opens a Postgres connection per request: cache the postgres value for a short TTL or rate-limit it, and list the version disclosure in the threat model.
