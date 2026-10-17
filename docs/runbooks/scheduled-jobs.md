# Runbook: scheduled jobs (OPS-13)

Recurring work (monthly reviews, the overdue restore-test check, retention sweeps) runs as ordinary
Procrastinate jobs. A scheduler only **triggers** them: it runs one command in the API image and
holds no business logic. This works the same on Coolify now and on AWS later.

```bash
python -m aip.modules.ops.schedule enqueue <job> --all-tenants
python -m aip.modules.ops.schedule enqueue <job> --tenant <tenant-id> [--tenant <tenant-id> ...]
python -m aip.modules.ops.schedule check
```

## How it behaves

- `<job>` must be a registered job type (a module's `jobs.py`). An unknown name exits **2** and
  lists the registered ones.
- Each tenant gets its own job, enqueued as `aip_app` inside that tenant's `with_tenant`
  transaction, as a request would do. The worker (`aip_jobs`) then runs it as usual: retries,
  backoff, `job.failed` and the My jobs / admin queue views all apply.
- `--all-tenants` takes every tenant whose status is `active`, through `ops_active_tenant_ids()`
  (ADR 0032). Suspended, provisioning and offboarded tenants are skipped.
- **Firing twice is safe.** The idempotency key is `schedule:<job>:<period>`, and the period comes
  from the job's `[[schedules]]` entry (`month` by default: `2026-10`; `week`: `2026-W42`; `day`:
  `2026-10-16`; `hour`: `2026-10-16T13`). A second trigger in the same period changes nothing. Pass
  `--period` to re-run a specific period on purpose.
- The command prints one line per tenant (`<tenant>: <job> <period> -> job <id> (queued)`) and
  exits 0.

## Declaring a schedule

In the owning module's `manifest.toml`:

```toml
[[schedules]]
job = "security.restore_test_overdue"   # a job type registered in the module's jobs.py
cron = "0 3 1 * *"                       # five fields, UTC
period = "month"                         # hour | day | week | month (the idempotency window)
```

`python -m aip.modules.ops.schedule check` (also a unit test) fails if a schedule names a job that is
not registered. The manifest is the list of what must be scheduled. The trigger below is set up
once per entry.

## Coolify (now)

For each `[[schedules]]` entry, on the **api** resource: *Scheduled Tasks → Add*:

| Field | Value |
|---|---|
| Name | the job type, e.g. `security.restore_test_overdue` |
| Command | `python -m aip.modules.ops.schedule enqueue security.restore_test_overdue --all-tenants` |
| Frequency | the entry's `cron`, e.g. `0 3 1 * *` |
| Container | `api` |

The task runs in the api container, so it has `DATABASE_URL` (aip_app) and the same image as the
worker. Check the task's last run log in Coolify: it should end with `N tenant(s)`.

## AWS: EventBridge Scheduler → ECS RunTask (OPS-15 creates this)

One schedule per `[[schedules]]` entry. No Lambda.

- **Schedule**: `cron(0 3 1 * ? *)` (EventBridge's six-field form of the manifest's cron), time zone
  `UTC`, flexible time window **off**.
- **Target**: ECS `RunTask` on the API cluster, launch type Fargate, the `aip-api` task definition
  (same image and secrets as the API service: `DATABASE_URL` for aip_app, `DB_SSLMODE=verify-full`),
  private subnets and the API security group, with this container override:

  ```json
  {"containerOverrides": [{"name": "api", "command": [
    "python", "-m", "aip.modules.ops.schedule", "enqueue",
    "security.restore_test_overdue", "--all-tenants"
  ]}]}
  ```

- **Retry policy**: 2 retries and a 1-hour maximum event age. A retry in the same period enqueues
  nothing new, because the idempotency key makes it safe.
- **Dead-letter queue**: an SQS queue alarmed in CloudWatch, so a schedule that never ran is visible.
- **Scheduler role**: `ecs:RunTask` on the task definition and `iam:PassRole` for its task and
  execution roles, nothing else.

## Checking a run

- Coolify: the scheduled task's log. AWS: the stopped task's CloudWatch log stream.
- Then the jobs themselves: `GET /api/v1/admin/jobs?jobType=<job>` as a tenant's jobs admin, or the
  `jobs` table (`idempotency_key = 'schedule:<job>:<period>'`).
- A tenant missing from the run is not `active`. Check `tenants.status`.
