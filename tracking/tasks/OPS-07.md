# OPS-07 — OpenTofu baseline for staging and the build-promote pipeline
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`infra/terraform` with OpenTofu; SPAs on S3 + CloudFront with `/api/*` to the ALB), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (api and worker from one Python image; Redis is cache only, no durability; sandbox one-shot tasks), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (SSE-KMS, per-tenant prefix policy), [0002](../../docs/adr/0002-data-access-and-migrations.md) (Postgres 16, roles)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Create the OpenTofu IaC for the AWS Sydney staging environment and a build-once, scan, sign, promote workflow. Overlap note: OPS-09 (build, scan, ECR push, staging deploy, smoke) and OPS-10 (cosign, production promotion, rollback) also specify `.github/workflows/build-promote.yml`; if either has merged, extend that workflow rather than replacing it, and keep this task's pipeline steps to what is not yet there.

- **files**:
  - infra/terraform/modules/network/main.tf
  - infra/terraform/modules/data/main.tf
  - infra/terraform/modules/app/main.tf (ECS Fargate api + worker services, ALB, S3 + CloudFront for the web SPA)
  - infra/terraform/envs/staging/main.tf
  - infra/terraform/policy/ (conftest/OPA rules)
  - .github/workflows/build-promote.yml
- **steps**:
  - 1. Network module: VPC with private subnets across 2 AZs, public subnets for the ALB only, NAT, and VPC endpoints for S3, ECR, Secrets Manager and KMS.
  - 2. Data module: RDS Postgres 16 Multi-AZ with PITR (35 days), parameter group allowing ltree, pg_trgm, pgvector and pgcrypto; ElastiCache Redis (cache, rate limits, session cache and pub/sub only — no snapshot/durability requirement, per ADR 0003); S3 bucket with SSE-KMS, block public access, versioning, and a bucket policy per tenant prefix (`tenants/<tenant_id>/`) that rejects any `x-amz-server-side-encryption-aws-kms-key-id` other than that tenant's key (keys created by TENANCY-05; the module takes a `tenant_keys` map variable).
  - 3. App module: one ECS Fargate cluster; services `api` (uvicorn behind the ALB) and `worker` (`python -m aip.worker`) both from the `aip/api` image with different commands; small sizes; Secrets Manager references for `aip_app`, `aip_jobs` and the migrator (`aip_owner`) credentials; a task definition family `sandbox-*` placeholder for ECS RunTask; S3 + CloudFront for the web SPA with `/api/*` path-routed to the ALB so cookies are same-origin `__Host-` cookies.
  - 4. Staging composition in `envs/staging` with region `ap-southeast-2` and an S3 + DynamoDB (or S3 native lock) state backend.
  - 5. In build-promote.yml build the `apps/api` image once (`apps/api/Dockerfile`, uv-based) and the web bundle once (`pnpm --filter web build`), scan the image with Trivy, sign it with cosign, and promote the same digest (and the same bundle artifact) to staging then production with a manual approval on the `production` environment.
  - 6. Rollback: on a failed `/api/v1/health/ready` after deploy, redeploy the previous image digest and restore the previous web bundle prefix.
- **acceptance**:
  - `tofu validate` and `tofu plan` are clean for staging.
  - The promoted digest is identical across environments.
  - Production deploy needs approval.
  - No S3 bucket exists without SSE-KMS.
- **tests**:
  - **e2e**:
    - Merge to main deploys to staging and `GET /api/v1/health/ready` returns 200.
  - **integration**:
    - `tofu plan` against staging shows no unexpected destroys.
    - Deploy digest X then force a failing health check. Expected: the workflow redeploys the prior digest.
  - **unit**:
    - `tflint` and `tofu fmt -check -recursive infra/terraform` pass.
    - Policy test (`conftest test` on `tofu show -json` plan output): an `aws_s3_bucket` without a server-side encryption configuration is rejected; an ElastiCache or RDS resource without encryption at rest is rejected.
