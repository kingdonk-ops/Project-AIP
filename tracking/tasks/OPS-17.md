# OPS-17 — Handler DB role + tenant fan-out for periodic jobs

<!-- hand-edited: merged OPS-18 (Part B) per board re-draw 2026-10-17 -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-05, OPS-02, OPS-13 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0016, 0030
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), findings **H3** (Part A), **M9** (Part B)

> Part A (was OPS-17) gives handlers a role that can write tenant tables and emit events; Part B (was OPS-18)
> uses that role to run periodic per-tenant work. Part B depends on Part A, so they are one task.

## Part A — job handlers can write domain tables and emit events (review 11 H3)

### Background

Handlers run inside `with_tenant(tenant_id, engine=get_jobs_engine())` (`modules/ops/runner.py`), so as
`aip_jobs`. `aip_jobs` has no grants on tenant tables (the table template grants it nothing). The review saw only
SELECT plus column UPDATE on `domain_events`; since then OPS-03 (PR #100, ADR 0030 amendment) granted `aip_jobs`
INSERT on `domain_events`, so emitting now works and the tenant-table grants are the gap left. The only handlers
today (Keycloak session revocation, `ops.send_email`) touch no tenant table, so nothing breaks yet. UPLOADS-02
updates `upload_sessions` and emits `upload.completed`/`upload.rejected` inside its job, which would retry until it
dead-letters. No runner test has a handler that writes a tenant table.

### Spec

A job handler can write tenant tables and emit domain events, so UPLOADS-02, AUDIT-03, imports and PDF jobs do not fail with `permission denied`.

- **files**:
  - docs/adr/0016-job-runner-semantics.md (amendment)
  - apps/api/aip/modules/ops/runner.py
  - apps/api/aip/modules/ops/tests/
  - db/ migrations or templates (only for option b)
- **steps**:
  - 1. Amend ADR 0016 choosing between: (a) run the handler transaction on the `aip_app` engine (RLS still applies through `with_tenant`) and keep `aip_jobs` for queue and status bookkeeping; (b) grant `aip_jobs` the `aip_app` table set (it already has INSERT on `domain_events`). The review recommends (a): simpler, least privilege.
  - 2. Implement the choice in the runner.
  - 3. Add a runner test whose handler writes a tenant table and emits an event, run as the real roles.
- **acceptance**:
  - A handler that inserts into a tenant table and emits an event succeeds, and the event reaches the outbox.
  - RLS still binds the handler to the job's tenant.
  - `aip_jobs` gains no privilege the ADR does not name.
- **tests**:
  - **integration**:
    - handler writes a `widgets` row and emits `widget.created` v1 → job succeeds, row and outbox event exist
    - the same handler for tenant A → no row visible in tenant B

## Part B — tenant fan-out for periodic jobs (merged from OPS-18, review 11 M9)

### Background

`UploadSessionService.expire_stale_sessions` (`uploads/service.py:248-251`) is called only by a test, although
UPLOADS-01 step 7 says it is scheduled. `snapshot_cli` needs explicit `--tenant` ids because `aip_jobs` cannot list
tenants (`entitlements/snapshot_cli.py:19`). Nothing schedules either, so stale upload sessions never expire,
`tenant_usage` is never snapshotted, and expired overrides are never swept (no audit event).

### Spec

Periodic per-tenant work runs for every active tenant: upload-session expiry and entitlement snapshots.

- **files**:
  - a migration adding `platform_active_tenant_ids()`
  - apps/api/aip/modules/ops/ (fan-out job)
  - apps/api/aip/modules/uploads/
  - apps/api/aip/modules/tenancy/entitlements/
- **steps**:
  - 1. Add a `SECURITY DEFINER` `platform_active_tenant_ids()` (pinned `search_path`, PUBLIC revoked) executable by `aip_jobs`.
  - 2. Add a periodic fan-out job that enqueues one job per active tenant.
  - 3. Schedule upload-session expiry and the entitlement snapshot through it (via the OPS-13 trigger). The per-tenant work runs under the Part A handler role.
- **acceptance**:
  - One tick enqueues one job per active tenant and none for suspended tenants.
  - Stale upload sessions expire; `tenant_usage` gets a snapshot; expired overrides are swept with an audit event.
- **tests**:
  - **integration**:
    - two active tenants and one suspended → two jobs enqueued
    - a stale upload session in tenant A → expired after the job; tenant B untouched
