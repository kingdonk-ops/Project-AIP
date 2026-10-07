# UPLOADS-05 — Per-file-type policy table + storage quota counters

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | UPLOADS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (RLS that permits reading platform rows), [0008](../../docs/adr/0008-entitlements-and-commercial-model.md) (storage_gb is an entitlement)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/uploads/data-model.md) (`file_type_policies`, `storage_quotas`)

## Spec

Replace the hard-coded allow-list with platform, tenant and project policy rows capped by platform limits. Reserve storage quota atomically at session creation so concurrent uploads can't overrun it (tag: harden).

- **files**:
  - db/migrations/<timestamp>_uploads_policies_quotas.sql
  - apps/api/src/modules/uploads/policy/policy-resolver.ts
  - apps/api/src/modules/uploads/policy/policies.controller.ts
  - apps/api/src/modules/uploads/quota/quota.service.ts
  - apps/api/src/modules/uploads/sessions.service.ts
  - apps/api/src/modules/uploads/pipeline/pipeline.ts
  - apps/api/src/modules/uploads/tests/policy-resolver.spec.ts
  - apps/api/src/modules/uploads/tests/quota.int.spec.ts
- **steps**:
  - 1. Migration:
    - `file_type_policies` with the data-model columns. `tenant_id` is nullable, and null marks a platform default row. RLS: `USING (tenant_id IS NULL OR tenant_id = <ctx>)` and `WITH CHECK (tenant_id = <ctx>)`, so the app can read platform rows but never write them.
    - Unique `(coalesce(tenant_id, zero-uuid), coalesce(project_id, zero-uuid), detected_mime) where deleted_at is null`.
    - `storage_quotas` with `limit_bytes`, `used_bytes`, `reserved_bytes` and `warn_threshold_pct`, plus check constraints `used_bytes >= 0`, `reserved_bytes >= 0`.
    - Seed the platform rows from `platform-limits.ts` (UPLOADS-01): jpeg, png, heic and webp at 50 MiB with `preview_mode thumbnail` and `strip_exif_gps true`; pdf at 200 MiB, `preview_mode none`; csv and text at 20 MiB; xlsx and docx at 50 MiB with ratio 100.
  - 2. `policy-resolver.ts`: `resolvePolicy(tenantId, projectId, mime)` looks for a project row, then a tenant row, then the platform row. If none is found, or the row has `allowed = false`, it denies. It returns the effective row and its id. Platform ceilings in code always cap the result: a tenant row can lower limits but never raise them above the ceilings, and it can never allow a type the platform denies (SVG, HTML, executables).
  - 3. Use the resolver in `sessions.service` (declared mime and size) and in the UPLOADS-02 `magic_bytes` and `size_cap` stages (detected mime). Store `stored_files.policy_id` at release.
  - 4. `quota.service.ts`:
    - `reserve(tenantId, projectId, bytes)` is a single `UPDATE storage_quotas SET reserved_bytes = reserved_bytes + $1 WHERE ... AND used_bytes + reserved_bytes + $1 <= limit_bytes RETURNING id`. It checks the tenant row and the project row if one exists, in one transaction. If no row is updated, it returns 413 `QUOTA_EXCEEDED` and `emit('upload.quota_exceeded', ...)`.
    - `commit(sessionId, actualBytes)` on release does `reserved -= declared, used += actual`.
    - `release(sessionId)` on reject, expire or abort does `reserved -= declared`.
  - 5. Default tenant limit: if ENT-01 is `done`, use `EntitlementService.check(tenant, 'storage_gb')`. Otherwise use config `UPLOADS_DEFAULT_TENANT_QUOTA_GB=100` and write a one-line stub follow-up task to switch to entitlements.
  - 6. Endpoints:
    - `GET /api/v1/uploads/policies` returns the effective rows (`uploads.view`).
    - `PUT /api/v1/uploads/policies/:mime {maxSizeBytes, allowed, scanDepth, previewMode, stripExifGps, projectId?}` (`uploads.policy.manage`). If the request exceeds a ceiling, it returns 422 `EXCEEDS_PLATFORM_LIMIT`.
    - `GET /api/v1/uploads/quota` returns `{limit, used, reserved, warn}` for the tenant and each project.

    The admin UI pages are R1 stubs.
- **acceptance**:
  - Tenant and project rows override platform defaults only within the ceilings.
  - Platform rows can be read but never written by tenants.
  - Concurrent sessions can never reserve more than the quota.
  - The counters stay consistent through release, reject, expiry and abort.
- **tests**:
  - **unit**:
    - The resolver with a pdf project row at 10 MiB, a tenant row at 50 MiB and the platform at 200 MiB → returns the project row. Without the project row → the tenant row.
    - A tenant row with `image/svg+xml allowed:true` → the resolver still denies, and `PUT` → 422.
    - `PUT` pdf `maxSizeBytes 2 GiB` with a 200 MiB ceiling → 422 `EXCEEDS_PLATFORM_LIMIT`.
  - **integration**:
    - These use Testcontainers Postgres and object storage. A tenant quota of 10 MiB, then 3 sessions of 4 MiB created with `Promise.all` → exactly 2 succeed and 1 returns 413. `domain_events` has 1 `upload.quota_exceeded` row.
    - Release one session with 3 MiB actual → `used 3 MiB` and `reserved 4 MiB`. Reject the other → `reserved 0`.
    - A tenant pdf row at 20 MiB, then a session for a 30 MiB pdf → 413.
    - A `tenant-b` session reads `file_type_policies` → platform rows only, none of `kaefer-demo`'s rows.
    - `UPDATE file_type_policies SET max_size_bytes = 1 WHERE tenant_id IS NULL` as `aip_app` → 0 rows updated.
  - **e2e**:
    - Playwright API project. A `kaefer-demo` admin `PUT`s pdf `maxSizeBytes` to 1 MiB, then a user creates a 2 MiB pdf session → 413 with `messageKey 'uploads.error.too_large'`. `GET /quota` shows the reserved bytes for an in-flight 0.5 MiB session.
