# OPS-13 — Scheduled job trigger: one command for Coolify cron and EventBridge Scheduler

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | OPS-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0003 (Procrastinate jobs, outbox), 0016 (job runner semantics)

## Spec

Recurring work (monthly reviews, the overdue restore-test check, retention sweeps) runs as ordinary
Procrastinate jobs. Add one entry point that enqueues a named, registered job, so the trigger can be a
Coolify scheduled task now and Amazon EventBridge Scheduler (ECS RunTask with the API image) in AWS,
with no business logic in Lambda.

- **files**:
  - apps/api/aip/modules/ops/schedule.py
  - apps/api/aip/modules/ops/tests/test_schedule.py
  - docs/runbooks/scheduled-jobs.md
- **steps**:
  - 1. `python -m aip.modules.ops.schedule enqueue <job-name> [--tenant <id>|--all-tenants]` looks the job
    up in the handler registry and enqueues it as `aip_jobs`; unknown names exit non-zero.
  - 2. A per-schedule idempotency key (job name + period, e.g. `2026-10`) so a trigger that fires twice
    enqueues once.
  - 3. Declare schedules in module manifests (`[[schedules]] job = ..., cron = ...`) and add a check that
    every declared schedule names a registered job.
  - 4. The runbook shows the Coolify scheduled-task setup and the EventBridge Scheduler to ECS RunTask
    shape that OPS-15 creates.
- **acceptance**:
  - Running the command twice for the same period leaves one job.
  - An unknown job name exits 2 with a message.
- **tests**:
  - **unit**:
    - A manifest schedule naming an unregistered job fails the check.
  - **integration**:
    - Enqueue twice with the same period: one row in the Procrastinate jobs table.
    - `--all-tenants` enqueues one job per active tenant.
