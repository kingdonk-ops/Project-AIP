# UPLOADS-02 — Scan worker: ClamAV, magic bytes, caps, fail-closed release

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-05, OPS-02, UPLOADS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (append-only grants), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (BullMQ queues per job class, tenant in payload, outbox), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/uploads/data-model.md) (`stored_files`, `scan_results`); for hardening intent: [`docs/reviews/01-security.md`](../../docs/reviews/01-security.md) risk #5 and the UPLOADS-xx line under "Missing tasks"

## Spec

After confirm, a worker job checks the size cap, magic bytes, the decompression and pixel caps, and ClamAV, in that order, recording every stage. Only that worker can release a clean object into tenant storage. Any error fails closed, and the upload.completed or upload.rejected event is written through the outbox (tag: harden).

- **files**:
  - db/migrations/<timestamp>_uploads_stored_files_scan.sql
  - apps/api/src/modules/uploads/pipeline/pipeline.ts
  - apps/api/src/modules/uploads/pipeline/magic-bytes.ts
  - apps/api/src/modules/uploads/pipeline/caps.ts
  - apps/api/src/modules/uploads/pipeline/clamav-client.ts
  - apps/api/src/modules/uploads/pipeline/release.ts
  - apps/api/src/modules/uploads/files.controller.ts
  - apps/api/src/modules/uploads/api.ts
  - apps/api/src/modules/uploads/tests/pipeline.spec.ts
  - apps/api/src/modules/uploads/tests/pipeline.int.spec.ts
  - apps/worker/src/processors/uploads-scan.processor.ts
  - infra/docker-compose.yml (add `clamav` service on the internal network only)
  - the ARCH-03 dependency-cruiser config (one rule: "no direct S3")
  - e2e/web/uploads-scan.spec.ts
- **steps**:
  - 1. Migration:
    - `stored_files` with the data-model columns: `scan_status` check `quarantined|clean|failed`, `preview_status` check `pending|ready|none|failed`, `detected_mime`, `size_bytes`, `sha256`, `storage_key`, `uploaded_by`, `legal_hold`, and soft delete.
    - `scan_results`, which is append-only: `stage` check `clamav|magic_bytes|size_cap|ratio_cap|rescan`, `outcome` check `pass|fail|error`, `signature_db_version`, `detail jsonb`, and `REVOKE UPDATE, DELETE, TRUNCATE ... FROM aip_app`.
    - The FK `upload_sessions.file_id → stored_files.id`.
    - FORCE RLS on both new tables.
  - 2. `confirm` (UPLOADS-01) enqueues job `uploads.scan` on queue `uploads-scan` through the OPS-02 runner, with `jobId = sessionId` (idempotent), payload `{tenantId, sessionId}`, timeout 120 s and 3 attempts. `apps/worker/src/processors/uploads-scan.processor.ts` only calls `UploadsApi.runScanPipeline(ctx, sessionId)` inside `withTenant`. It imports nothing else from the module.
  - 3. `pipeline.ts`: set the status to `scanning` and stream the quarantine object once, computing `sha256` while streaming. Run the stages in order, writing one `scan_results` row per stage and stopping at the first `fail` or `error`:
    - (a) `size_cap`: the actual size is at most the declared size and the platform limit.
    - (b) `magic_bytes` (the `file-type` package on the first 4 KB): the detected mime is allowed, and its family is compatible with the declared one. `text/csv` and `text/plain` must be valid UTF-8 with no NUL bytes. Any declared or detected SVG or HTML fails.
    - (c) `ratio_cap`:
      - For ZIP-based OOXML, read the central directory only: total uncompressed ÷ compressed ≤ 100, entries ≤ 10,000, no nested archives, no absolute or `..` paths.
      - For images, read the header dimensions only: ≤ 100 megapixels.
    - (d) `clamav`: clamd `INSTREAM` over TCP with a 60 s timeout. Record the `VERSION` string as `signature_db_version`.
  - 4. Fail closed:
    - A stage `error` (a timeout, clamd unreachable, a parse exception) throws so that BullMQ retries.
    - On the last attempt, the session becomes `rejected` with reason `scan_error`.
    - A `fail` rejects immediately with the stage as the reason.
    - Every rejection emits `upload.rejected {sessionId, projectId, reason}` through `emit(tx, ...)` (ARCH-05) and keeps the quarantine object for review. A 30-day quarantine lifecycle rule is noted for OPS-06.
  - 5. `release.ts` is called only from the pipeline. It is not exported from `api.ts`, and no controller can call it.
    - Server-side copy to the released bucket at key `s3Key(tenantId, 'files', fileId)`, with SSE-KMS and the tenant context.
    - Insert `stored_files` with `scan_status = 'clean'`, the detected mime, size and sha256.
    - Set the session to `released` with `file_id`.
    - `emit('upload.completed', 1, {sessionId, fileId, projectId, detectedMime, sizeBytes, sha256})` in the same transaction, then delete the quarantine object after commit.
  - 6. `GET /api/v1/uploads/files/:id/url` returns a presigned GET (TTL 5 min, `Content-Disposition: attachment`, served from the separate `FILES_ORIGIN` host) only when `scan_status = 'clean'` and `PolicyService.can(actor, 'uploads.view', {projectId})`. Any other status gives 409 `NOT_RELEASED`.
  - 7. Schedule `expireStaleSessions` (UPLOADS-01) as a repeatable job every 15 minutes.
  - 8. Add a dependency-cruiser rule that forbids importing `@aws-sdk/client-s3` or `platform/capabilities/object-store` from anywhere except `platform/capabilities/**` and `modules/uploads/**`.
  - 9. compose: add `clamav/clamav:stable` with freshclam enabled, attached only to an `internal: true` network shared with the worker.
- **acceptance**:
  - A file reaches `stored_files` as `clean` only after all four stages pass.
  - A scanner error, timeout or outage never releases anything.
  - `scan_results` cannot be edited by the app role.
  - Each released or rejected session has exactly one `upload.completed` or `upload.rejected` outbox row.
  - Files are served only when clean.
  - The "no direct S3" lint fails CI on a violating import.
- **tests**:
  - **unit**:
    - `magicBytes(Buffer 'MZ\x90\x00...', declared 'image/jpeg')` → `fail`, `detail.detected = 'application/x-msdownload'`.
    - `magicBytes(Buffer '%PDF-1.7\n...', 'application/pdf')` → `pass`.
    - A PNG header declaring 20000×20000 → `ratio_cap fail`, `detail.megapixels = 400`.
    - A crafted xlsx whose central directory declares 1 GiB uncompressed from a 1 MiB compressed size → `ratio_cap fail`, `detail.ratio = 1024`.
    - A zip entry named `../../x` → `ratio_cap fail`.
    - The `clamav-client` against a stub socket that never answers → `error` after the timeout. The pipeline reducer turns any `error` on the last attempt into `rejected / scan_error`.
  - **integration**:
    - These use Testcontainers Postgres, Redis, MinIO or RustFS and `clamav/clamav`. Upload and confirm a clean `sample.pdf`, then run the worker → the session is `released`, there is 1 `stored_files` row (`clean`) and 4 `scan_results` rows, all `pass`. There is 1 `upload.completed` row in `domain_events`, the quarantine object is gone, and the released key starts with `tenant/<A>/files/`.
    - The EICAR string as `text/plain` → `rejected`. The `clamav` row is `fail`, and `detail.signature` contains `EICAR`. There is 1 `upload.rejected` event and no `stored_files` row.
    - A `.jpg`-named upload whose bytes are HTML, declared `image/jpeg` → rejected at `magic_bytes`.
    - Stop the clamav container → after 3 attempts the session is `rejected / scan_error`, and nothing is released.
    - Enqueue the same session twice → 1 `stored_files` row.
    - `GET /files/:id/url` for the rejected session's file → 409 or 404. For the clean file → the URL downloads bytes with the same sha256. A `tenant-b` user → 404.
    - As `aip_app`: `UPDATE scan_results SET outcome='pass'` → `permission denied`.
    - A fixture `apps/api/src/modules/projects/bad.ts` importing `@aws-sdk/client-s3` → dependency-cruiser exits non-zero.
  - **e2e**:
    - Playwright API project on the compose stack. Upload the EICAR string (generated at runtime, never committed) → status `rejected` within 60 s. Upload `e2e/fixtures/photo.jpg` → `released`, and the downloaded bytes match the source sha256.
