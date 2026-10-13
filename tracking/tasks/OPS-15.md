# OPS-15 — CloudWatch alarms, EventBridge schedules and secret-rotation Lambdas

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-07, OPS-13, SECURITY-10 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0003 (jobs), 0004 (infra/terraform), the secret-rotation ADR from SECURITY-10
4. `apps/api/aip/platform/observability/` (JSON log fields and OTLP tracing)

## Spec

Add the operational layer for AWS in `ap-southeast-2`: CloudWatch log groups, metric filters and alarms
(the custom error sink), the ADOT collector sidecar, EventBridge Scheduler schedules that run OPS-13's
enqueue command, and Secrets Manager rotation on a 90-day schedule using the strategy SECURITY-10 chose.

- **files**:
  - infra/terraform/modules/observability/main.tf
  - infra/terraform/modules/schedules/main.tf
  - infra/terraform/modules/secrets/main.tf
  - infra/terraform/envs/staging/main.tf
- **steps**:
  - 1. Log groups per service with a retention policy; api and worker use the `awslogs` driver (the
    app already writes one JSON object per line to stdout).
  - 2. Metric filters on `level=error` and on 5xx access lines; alarms on those, ALB 5xx and target
    health, RDS CPU, free storage and connections, ElastiCache memory, and the age of the oldest queued
    job; all go to one SNS topic.
  - 3. ADOT collector sidecar in the api and worker tasks; set `OTEL_EXPORTER_OTLP_ENDPOINT` to it.
  - 4. EventBridge Scheduler: one schedule per manifest `[[schedules]]` entry (OPS-13), each an ECS
    RunTask of the API image running the enqueue command. The DR drill (OPS-08) is the only schedule
    that may call a Lambda, because it acts on infrastructure (restore a snapshot, check it, delete it).
  - 5. Secrets Manager rotation every 90 days for every secret listed in the SECURITY-10 ADR, with the
    rotation Lambdas it chose; where the ADR needs it, the rotation's last step forces a new ECS deployment.
- **acceptance**:
  - `tofu plan` is clean for staging.
  - An error log line written in staging raises the error alarm within 5 minutes.
  - A schedule fires and its job appears in the jobs table.
  - A rotation run completes with no 5xx on the ALB.
- **tests**:
  - **unit**:
    - Policy test: every Secrets Manager secret has rotation enabled at 90 days or less.
    - Every manifest schedule has a matching EventBridge schedule (generated, compared in CI).
  - **e2e**:
    - In staging, trigger rotation of `aip_app` while the smoke test runs. Expected: the smoke test stays green.
