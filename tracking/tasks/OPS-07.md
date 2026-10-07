# OPS-07 — Terraform baseline for staging and the build-promote pipeline

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Create the IaC for the AWS Sydney environment and a build-once, scan, sign, promote workflow.

- **files**:
  - infrastructure/terraform/modules/network/main.tf
  - infrastructure/terraform/modules/data/main.tf
  - infrastructure/terraform/envs/staging/main.tf
  - .github/workflows/build-promote.yml
- **steps**:
  - 1. Write the network module: VPC with private subnets across 2 AZs.
  - 2. Write the data module: RDS Postgres Multi-AZ with PITR, ElastiCache, S3 with SSE-KMS and a per-tenant prefix policy.
  - 3. Add the ECS Fargate service module with small sizes, plus Secrets Manager references.
  - 4. Add a staging environment composition with region ap-southeast-2.
  - 5. In build-promote.yml build the image once, scan with Trivy, sign with cosign, and promote the same digest to staging then production with a manual approval.
  - 6. Add rollback: redeploy the previous digest on a failed health check.
- **acceptance**:
  - tofu validate and tofu plan are clean.
  - The promoted digest is identical across environments.
  - Production deploy needs approval.
- **tests**:
  - **e2e**:
    - Merge to main deploys to staging and /health/ready returns 200.
  - **integration**:
    - tofu plan against staging shows no unexpected destroys.
    - Deploy digest X then a failing health check: the workflow redeploys the prior digest.
  - **unit**:
    - tflint and tofu fmt -check pass.
    - Policy test: no S3 bucket resource without server_side_encryption.
