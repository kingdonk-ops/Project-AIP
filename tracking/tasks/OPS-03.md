# OPS-03 — Jobs API: my jobs, admin queue, cancel with permission

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | OPS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Expose job endpoints with ownership and permission checks.

- **depends on**:
  - OPS-02
- **files**:
  - backend/app/modules/ops/jobs/router.py
  - backend/tests/ops/test_jobs_api.py
  - frontend/src/features/jobs/MyJobsDrawer.tsx
- **steps**:
  - 1. GET /jobs/mine returns only the caller's jobs.
  - 2. GET /admin/jobs with filters, requiring jobs:admin.
  - 3. POST /jobs/{id}/cancel allowed for the requester or jobs:admin; a running job gets a cancel flag that the wrapper checks.
  - 4. POST /jobs/{id}/retry for failed jobs.
  - 5. Emit job.completed and job.failed events to notifications.
  - 6. Build a small drawer component with filter chips and progress.
- **acceptance**:
  - A user cannot see or cancel another user's job.
  - Cancel of a finished job returns 409.
  - The failure detail shows the correlation id.
- **tests**:
  - **e2e**:
    - User starts an export, the drawer shows progress, then Completed with an Open result action.
  - **integration**:
    - u1 GET /jobs/mine does not include u2's job.
    - u2 POST cancel on u1's job returns 403.
    - Admin cancel of a queued job gives status cancelled.
    - Cancel of a succeeded job returns 409.
  - **unit**:
    - can_cancel(requester=u1, job.requested_by=u2, no admin) is false.

## Carried forward from TENANCY-02 (not built there)

- `aip/platform/jobs/tenant_guard.py` (`TenantJobPayload`, `defer_for_tenant`, `tenant_task`): a payload type that requires a validated `TenantId`, and a deferral helper that refuses to enqueue a tenant job without one. It lives in the jobs code OPS-02 owns, so it was left out of TENANCY-02. Build it with the jobs API.
