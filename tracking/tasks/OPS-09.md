# OPS-09 — Build once, scan, push to ECR, deploy staging, smoke

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

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
3. ADRs: 0004 (`infra/terraform`, `apps/*` Dockerfiles), 0002 (migrations run as the migrator role over a direct connection), 0007 (M0 exit: the staging URL is live)
4. Only if the step needs it: [`tracking/tasks/OPS-07.md`](OPS-07.md) for the network, data and ECS baseline this task deploys onto

## Spec

On every merge to main, build the api, worker and web images once, scan them, push them by digest to ECR with keyless CI credentials, run migrations, deploy that exact digest to the AWS staging ECS services, and prove it with a smoke check. Signing, production promotion and rollback are OPS-10.

- **files**:
  - .github/workflows/build-promote.yml
  - infra/terraform/modules/ecr/main.tf
  - infra/terraform/modules/ci-oidc/main.tf
  - infra/terraform/envs/staging/main.tf (add the two module blocks only)
  - infra/deploy/render-taskdef.ts
  - infra/deploy/run-migrations.ts
  - infra/deploy/smoke.ts
  - infra/deploy/tests/
- **steps**:
  - 1. OPS-07 is the infra baseline. Its file list says `infrastructure/terraform`, but ADR 0004 says `infra/terraform`. Use whatever path is on main. If both exist, stop and flag it.
  - 2. Add the ECR module: repositories `aip/api`, `aip/worker` and `aip/web` with `image_tag_mutability = IMMUTABLE`, scan on push, KMS encryption, and a lifecycle rule that never expires an image deployed in the last 90 days.
  - 3. Add the CI OIDC module: a GitHub OIDC provider and the role `aip-ci-staging`, trusted only for `repo:<org>/<repo>:ref:refs/heads/main` and the `staging` environment. Its policy allows only ECR push for the three repos, `ecs:RegisterTaskDefinition`/`UpdateService`/`DescribeServices`/`RunTask` on the staging cluster, `iam:PassRole` for the task roles, and reading the staging migrator secret. There are no long-lived AWS keys in GitHub.
  - 4. In build-promote.yml, the `build` job runs on push to main. It uses `docker buildx` with a cache, builds each image once from `apps/<app>/Dockerfile`, tags it with `${GITHUB_SHA}`, pushes it, and records the image digests as a job output and a `digests.json` artifact. Every later step references `repo@sha256:…`, never a tag.
  - 5. The `scan` job runs Trivy on each pushed digest and fails on CRITICAL or HIGH findings with a fix available. It uploads SARIF to code scanning. An ignore file is allowed only with an expiry date and a reason.
  - 6. The `deploy-staging` job (GitHub environment `staging`) first runs migrations: `run-migrations.ts` starts a one-off ECS task from the api image, running the DATABASE-08 runner as the migrator role (a direct connection, credentials from Secrets Manager), waits for it, and fails the deploy on a non-zero exit. Then `render-taskdef.ts` takes the current task definition, replaces only the image with the digest and sets `GIT_SHA`, registers it, and updates api, worker and web. The job waits for `services-stable` with a 15-minute timeout.
  - 7. In smoke.ts, run against the staging URL with retries for up to 3 minutes. `GET /api/v1/health/ready` must return 200. `GET /api/v1/platform/version` must have `commit` equal to `GITHUB_SHA`. `GET /login` must return 200 with a CSP header. The first two prove the new digest is serving. If TESTING-09 is merged, also run its `@staging` Playwright spec. A smoke failure fails the workflow; rollback is OPS-10.
  - 8. Gate the workflow: build runs only after the CI workflow (lint, unit, integration, e2e) succeeds for the same SHA (`workflow_run`, or `needs` if it is in one file). Use concurrency group `deploy-staging` with no cancellation of an in-progress deploy.
- **acceptance**:
  - A merge to main produces one digest per app, and the same digest is scanned, deployed and reported by `/platform/version`.
  - A HIGH vulnerability with a fix available blocks the deploy.
  - A failing migration stops the deploy before any service update.
  - The workflow has no AWS access keys; it assumes the OIDC role. The role cannot be assumed from a pull-request ref.
  - tofu validate, fmt and plan are clean for staging, with no unexpected destroys.
- **tests**:
  - **unit**:
    - render-taskdef with a task definition whose container `api` has image `…/aip/api:old`, and digest `sha256:abc`, returns image `…/aip/api@sha256:abc`, `GIT_SHA` set, and every other field unchanged (deep-equal apart from those two).
    - smoke with version `{commit:'deadbeef'}` and expected `cafef00d` exits 1 with "version mismatch". With matching commits and 200s it exits 0. With the first two attempts returning 503, it still passes within its retry window.
    - The `tflint` and `tofu fmt -check` jobs pass. A policy check (conftest/OPA) rejects an `aws_ecr_repository` with `MUTABLE` tags.
  - **integration**:
    - `act` (or a dry-run job on a branch with the deploy steps stubbed) on a commit with a known-vulnerable base image. Expected: the scan job fails and deploy-staging is skipped.
    - Make the migration task exit 1 on purpose. Expected: deploy-staging fails, and `aws ecs describe-services` shows the previous task definition still primary.
    - `tofu plan` on envs/staging shows only creates for ECR and OIDC resources.
  - **e2e**:
    - Merge a commit to main. Expected: within 30 minutes the staging `/api/v1/platform/version` returns that commit, and `aws ecr describe-images` shows the deployed digest with the tag equal to the SHA.
