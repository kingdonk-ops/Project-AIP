# OPS-14 — AWS services beyond the baseline: Keycloak, Gotenberg, KMS and SES

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-07, STACK-06 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0004 (infra/terraform, OpenTofu), 0005 (Keycloak), 0006 (per-tenant KMS keys)
4. `infra/docker-compose.yml` (the services this task mirrors in AWS)

## Spec

OPS-07 creates the network, RDS, ElastiCache, S3 and the api and worker services. Add the other services
the app needs in `ap-southeast-2` to the OpenTofu modules: Keycloak, Gotenberg, the per-tenant KMS keys,
and SES for transactional email.

- **files**:
  - infra/terraform/modules/identity/main.tf (Keycloak)
  - infra/terraform/modules/app/main.tf (Gotenberg, worker queue groups)
  - infra/terraform/modules/keys/main.tf (KMS)
  - infra/terraform/modules/email/main.tf (SES)
  - infra/terraform/envs/staging/main.tf
- **steps**:
  - 1. Keycloak: a Fargate service from a pinned 26.x image built with `kc.sh build` (production `start`,
    not `start-dev`), its own `keycloak` database on the RDS instance, its own ALB host rule, the realm
    and theme from `infra/keycloak`, and SMTP to SES.
  - 2. Gotenberg: an internal-only Fargate service (ECS Service Connect, no ALB route), reachable by the
    worker's `pdf` queue group only.
  - 3. KMS: a key per tenant from the `tenant_keys` input (TENANCY-05 creates them), with key policies
    that let only the api and worker task roles use them.
  - 4. SES: a verified domain identity with Easy DKIM, SPF and DMARC records, a configuration set, SNS
    topics for bounces and complaints, SMTP credentials in Secrets Manager for Keycloak, and an IAM
    policy letting the task role call `ses:SendEmail` from that domain only. Production access (out of
    the SES sandbox) is requested by hand and noted in the runbook.
- **acceptance**:
  - `tofu validate` and `tofu plan` are clean for staging.
  - Staff can sign in through the staging Keycloak, and its verify-email mail is delivered through SES.
  - Gotenberg cannot be reached from the internet.
- **tests**:
  - **unit**:
    - `tflint` and `tofu fmt -check -recursive infra/terraform` pass.
    - Policy test: a KMS key policy that grants `kms:*` to `*` is rejected.
  - **e2e**:
    - After a staging deploy, a smoke test signs in through Keycloak and renders a PDF through Gotenberg.
