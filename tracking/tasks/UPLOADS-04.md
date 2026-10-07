# UPLOADS-04 — EXIF/GPS policy + thumbnails in sandboxed worker

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | UPLOADS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (append-only; no PostGIS until needed), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (separate worker pools), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/uploads/data-model.md) (`file_capture_metadata`, `stored_files.thumbnail_key/preview_key/preview_status`); for the EXIF default: [`docs/reviews/01-security.md`](../../docs/reviews/01-security.md) risk #5

## Spec

For released images, write a sanitised shared copy (GPS stripped by project policy) and 320 and 1280 px thumbnails. The work runs in a network-isolated, resource-capped sandbox worker, and the capture metadata (device time, GPS where permitted, capture hash) is kept privately and immutably (tag: harden — absorbs the EXIF part of SECURITY-06).

> Default policy used (security review risk #5): **strip GPS from the shared copy and keep the original GPS
> privately**. The uploads README lists this as an open owner question. If the owner answers differently, only the
> default value in step 1 changes.

- **files**:
  - db/migrations/<timestamp>_uploads_capture_metadata.sql
  - apps/api/src/modules/uploads/derive/derive.service.ts
  - apps/api/src/modules/uploads/derive/sandbox-job.ts
  - apps/api/src/modules/uploads/derive/exif.ts
  - apps/api/src/modules/uploads/gps-policy.controller.ts
  - apps/api/src/modules/uploads/files.controller.ts
  - apps/api/src/modules/uploads/tests/exif.spec.ts
  - apps/api/src/modules/uploads/tests/derive.int.spec.ts
  - apps/worker/src/processors/uploads-derive.processor.ts
  - apps/worker/src/processors/uploads-sandbox.processor.ts
  - infra/docker-compose.yml (`worker-sandbox` service)
  - e2e/fixtures/photo-gps.jpg
  - e2e/web/uploads-exif.spec.ts
- **steps**:
  - 1. Migration:
    - `uploads_project_settings (tenant_id, project_id unique, gps_policy check 'strip_keep_private'|'strip_discard'|'keep' default 'strip_keep_private', timestamps)`.
    - `file_capture_metadata` with the data-model columns. Use `gps_lat numeric(9,6)` and `gps_lon numeric(9,6)` instead of a PostGIS point (ADR 0002: PostGIS only when a module needs it), plus `private_key`. It is append-only, with `REVOKE UPDATE, DELETE, TRUNCATE ... FROM aip_app`.
    - `stored_files.sanitised_at timestamptz null`.
    - FORCE RLS on the new tables.
  - 2. `upload.completed` for an image mime (jpeg, png, heic, webp) enqueues `uploads.derive` on queue `uploads-derive` (normal pool, `jobId = fileId`). `derive.service.ts`, run by the normal worker:
    - Reads the policy.
    - Creates presigned GET for the released original and presigned PUTs for the outputs, all with a 5-minute TTL.
    - Enqueues `uploads.sandbox` on queue `uploads-sandbox` and waits for its result through a BullMQ flow (parent/child).
  - 3. The sandbox job (`sandbox-job.ts`, run by `uploads-sandbox.processor.ts` in the `worker-sandbox` pool) receives **only URLs and the policy**: no DB, KMS or AWS credentials.
    - It uses `sharp` with `limitInputPixels: 100_000_000`, `failOn: 'error'` and `.rotate()` to apply the orientation.
    - It writes the sanitised full image with all EXIF, XMP and IPTC metadata removed (or with only GPS removed when the policy is `keep`, which keeps GPS) and 320 and 1280 px WebP thumbnails.
    - It returns `{exif: {capturedAt, gps?, make, model}, outputs}`.
    - It has a 60 s timeout.
  - 4. The `worker-sandbox` compose service and the Fargate task note: non-root uid 10001, `read_only: true`, tmpfs `/tmp`, `mem_limit: 512m`, `cpus: 1`, and only an `internal: true` network that reaches the object store. It has no internet egress.
  - 5. On sandbox success, `derive.service`:
    - Overwrites the shared object with the sanitised copy.
    - If the policy keeps GPS privately, stores the original under `s3Key(tenantId, 'originals', fileId)` (a restricted prefix).
    - Inserts `file_capture_metadata`: `device_captured_at`, `gps_*` (only if the policy is not `strip_discard`), `capture_hash` = the UPLOADS-02 original sha256, `device_info`.
    - Sets `thumbnail_key`, `preview_key`, `preview_status 'ready'` and `sanitised_at`.
  - 6. On failure (a decode error, the pixel limit, or a timeout after 2 attempts), set `preview_status = 'failed'`. The file stays unserved.
  - 7. Change `GET /files/:id/url` (UPLOADS-02) to return 409 `PROCESSING` for image types until `sanitised_at` is set. Add `GET /api/v1/uploads/files/:id/thumbnail?size=320|1280` (presigned, 5 min).
  - 8. Add `GET` and `PUT /api/v1/uploads/projects/:projectId/gps-policy` (`uploads.policy.manage`, declared in the manifest), and `GET /api/v1/uploads/files/:id/capture-metadata` (`uploads.capture_metadata.view`). Ordinary viewers never see GPS.
- **acceptance**:
  - No image is served before its shared copy is sanitised, and the shared copy contains no GPS unless the policy is `keep`.
  - The original GPS and device time are kept privately and immutably when the policy allows it.
  - Thumbnails exist for released images.
  - The sandbox has no egress and no credentials beyond 5-minute presigned URLs.
- **tests**:
  - **unit**:
    - `exif.ts` on `e2e/fixtures/photo-gps.jpg` (GPS −31.9505, 115.8605, DateTimeOriginal `2026:09:01 08:15:00`, Orientation 6): `readCapture` → `{gps:{lat:-31.9505, lon:115.8605}, capturedAt:'2026-09-01T08:15:00'}`. `sanitise` → `exifr.gps(output)` is `undefined`, and the output width and height are swapped (orientation applied).
    - `resolveGpsPolicy(undefined)` → `'strip_keep_private'`. With `'strip_discard'` → the capture GPS is null.
    - `sharp` on a 20000×20000 PNG → throws, and the job result is `failed: pixel_limit`.
  - **integration**:
    - These use Testcontainers Postgres, Redis and MinIO or RustFS, with both processors in-process. Release `photo-gps.jpg` into project P1 (default policy) → the shared object has no GPS. `file_capture_metadata` has `gps_lat -31.950500`. The thumbnails `thumb_320.webp` (width ≤ 320) and `thumb_1280.webp` exist, and `preview_status` is `ready`.
    - P2 with `strip_discard` → `gps_lat` is null, and there is no `originals/` object.
    - `GET /files/:id/url` before derive finishes → 409 `PROCESSING`. After it finishes → 200.
    - A truncated JPEG → `preview_status 'failed'`, and the URL stays 409.
    - `GET capture-metadata` without `uploads.capture_metadata.view` → 403. A `tenant-b` user → 404.
    - As `aip_app`: `UPDATE file_capture_metadata SET gps_lat = 0` → `permission denied`.
  - **e2e**:
    - Compose stack. From inside the `worker-sandbox` container, `node -e "fetch('https://example.com')"` → fails (no egress).
    - Playwright API: upload `photo-gps.jpg` and poll until the URL returns 200. Download it, and `exifr.gps` → `undefined`. `GET /thumbnail?size=320` → `image/webp`.
