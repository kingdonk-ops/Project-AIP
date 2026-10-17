# OPS-18 — Tenant fan-out for periodic jobs

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | OPS-13, OPS-17 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0016
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M9**. `UploadSessionService.expire_stale_sessions` (`uploads/service.py:248-251`) is called
only by a test, although UPLOADS-01 step 7 says it is scheduled. `snapshot_cli` needs explicit `--tenant` ids because
`aip_jobs` cannot list tenants (`entitlements/snapshot_cli.py:19`). Nothing schedules either, so stale upload sessions
never expire, `tenant_usage` is never snapshotted, and expired overrides are never swept (no audit event).

## Spec

Periodic per-tenant work runs for every active tenant: upload-session expiry and entitlement snapshots.

- **files**:
  - a migration adding `platform_active_tenant_ids()`
  - apps/api/aip/modules/ops/ (fan-out job)
  - apps/api/aip/modules/uploads/
  - apps/api/aip/modules/tenancy/entitlements/
- **steps**:
  - 1. Add a `SECURITY DEFINER` `platform_active_tenant_ids()` (pinned `search_path`, PUBLIC revoked) executable by `aip_jobs`.
  - 2. Add a periodic fan-out job that enqueues one job per active tenant.
  - 3. Schedule upload-session expiry and the entitlement snapshot through it (via the OPS-13 trigger).
- **acceptance**:
  - One tick enqueues one job per active tenant and none for suspended tenants.
  - Stale upload sessions expire; `tenant_usage` gets a snapshot; expired overrides are swept with an audit event.
- **tests**:
  - **integration**:
    - two active tenants and one suspended → two jobs enqueued
    - a stale upload session in tenant A → expired after the job; tenant B untouched
