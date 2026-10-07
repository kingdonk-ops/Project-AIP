# OPS-01 — Job tables and service

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

Persist job state and events in Postgres with idempotent creation.

- **files**:
  - backend/app/modules/ops/models.py
  - backend/migrations/versions/xxxx_ops_jobs.py
  - backend/app/modules/ops/jobs/service.py
  - backend/tests/ops/test_job_service.py
- **steps**:
  - 1. Write the migration for jobs (including the unique partial index tenant_id, job_type, idempotency_key) and job_events, with RLS.
  - 2. Add models.
  - 3. Implement create_job: on a duplicate idempotency key, return the existing job.
  - 4. Implement transition(job, new_status) enforcing queued to running to succeeded, failed or cancelled; terminal states are final.
  - 5. Write a job_event row for each transition.
  - 6. Generate a correlation_id if none is supplied.
- **acceptance**:
  - The same key gives the same job id.
  - Terminal jobs cannot change state.
  - Events are ordered.
- **tests**:
  - **e2e**:
    - None; the API is covered in OPS-03.
  - **integration**:
    - create_job twice with key 'k1': 1 row.
    - Same key in tenant B: separate job.
    - Transitions write 3 events: queued, running, succeeded.
  - **unit**:
    - transition(succeeded to running) raises InvalidTransition.
    - The correlation id is generated when None is passed.
