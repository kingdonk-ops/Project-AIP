# UPLOADS-03 — Resumable S3 multipart uploads

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | UPLOADS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md) (the open question "tus or S3 multipart")
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/uploads/data-model.md) (`upload_sessions.mode`, `s3_upload_id`, `chunk_size`, `parts_received`)

## Spec

Let large files (drawings, PDF packs, NDT data) survive dropped site connections. The upload uses S3 multipart with presigned part URLs, and S3's own part list is the source of truth for resume and completion (tag: harden).

> Decision used: **S3 multipart, not tus**, as the board title states. Before starting, check
> [OPEN-QUESTIONS.md](../OPEN-QUESTIONS.md) and the uploads README. If the owner has chosen tus, stop and
> re-scope. The choice is hidden behind `upload_sessions.mode`, so tus can be added later without a schema change.

- **files**:
  - apps/api/src/modules/uploads/multipart/part-plan.ts
  - apps/api/src/modules/uploads/multipart/multipart.service.ts
  - apps/api/src/modules/uploads/multipart/multipart.controller.ts
  - apps/api/src/modules/uploads/multipart/cleanup.ts
  - apps/api/src/modules/uploads/schemas.ts
  - apps/api/src/modules/uploads/tests/part-plan.spec.ts
  - apps/api/src/modules/uploads/tests/multipart.int.spec.ts
  - apps/api/src/platform/capabilities/object-store.ts (add `createMultipart`, `presignUploadPart`, `listParts`, `completeMultipart`, `abortMultipart` and `listMultipartUploads` to the interface and both adapters)
  - e2e/web/uploads-multipart.spec.ts
- **steps**:
  - 1. There is no new migration: `upload_sessions` from UPLOADS-01 already has `mode`, `s3_upload_id`, `chunk_size` and `parts_received`. If `parts_received` is missing, stop. A missing column means UPLOADS-01 deviated from the data model, and you should file a follow-up rather than adding a second migration here.
  - 2. `part-plan.ts` is pure:
    - `planParts(sizeBytes, chunkSize)` returns the part sizes.
    - `chunkSize` comes from config `UPLOADS_CHUNK_MIB` (default 8, allowed 5–64; S3 requires at least 5 MiB for every part except the last).
    - At most 10,000 parts, and a P0 maximum file size of 5 GiB (config). Larger gives 413.
    - `checkComplete(plan, listedParts)` returns `{ok}`, `{missing: number[]}` or `{badSize: number[]}`.
  - 3. `POST /api/v1/uploads/sessions` with `mode: 'multipart'` (also forced when `sizeBytes` is over 100 MiB):
    - Make the same policy, type, size and per-user checks as UPLOADS-01.
    - Call `createMultipart` on the tenant quarantine key with SSE-KMS and the tenant context.
    - Store `s3_upload_id` and `chunk_size`, with a TTL of `expires_at = now + 24 h`.
    - Return `{sessionId, partCount, chunkSize}`.
  - 4. `POST /api/v1/uploads/sessions/:id/parts {partNumbers: number[] (1..100)}` returns presigned `UploadPart` URLs with a 15-minute TTL. **Every call** re-checks the session owner, `expires_at`, the status (`requested|uploading`) and `PolicyService.can(actor, 'uploads.create', {projectId})`. Revoking project access mid-upload stops the next chunk. The first call sets the status to `uploading`.
  - 5. `GET /api/v1/uploads/sessions/:id` returns `{status, partCount, chunkSize, uploadedParts: [{partNumber, size}]}`, using **`listParts` from the store** rather than anything the client reports. Mirror the result into `parts_received` for display only.
  - 6. `POST /api/v1/uploads/sessions/:id/confirm` for multipart:
    - Call `listParts` and `checkComplete`. Missing parts give 409 `MISSING_PARTS`, and a non-last part with the wrong size gives 422 `INVALID_PART_SIZE`.
    - Check that the sum of the sizes equals `sizeBytes`.
    - Call `completeMultipart` with the ETags the store listed.
    - Set the status to `uploaded`. This is the same state single uploads reach, so the UPLOADS-02 scan runs unchanged on the reassembled object (type re-validated after reassembly). If UPLOADS-02 is already merged, make sure confirm enqueues the scan for both modes.
  - 7. `DELETE /api/v1/uploads/sessions/:id` calls `abortMultipart` and sets the status to `aborted`.
  - 8. `cleanup.ts`: `abortExpiredMultipart(now)` aborts sessions past `expires_at` and marks them `expired`. It also aborts orphan multipart uploads under `tenant/*/quarantine/` that are older than 24 h and have no live session. Export it from `api.ts`, so UPLOADS-02's runner (or OPS-02) can schedule it hourly.
- **acceptance**:
  - A 20 MiB upload interrupted after part 2 resumes by uploading only the missing part, and completes with a byte-identical object.
  - Confirm never trusts client-reported parts.
  - Permission, owner and expiry are checked on every part request.
  - Orphaned multipart uploads are cleaned up.
- **tests**:
  - **unit**:
    - `planParts(20 MiB, 8 MiB)` → `[8 MiB, 8 MiB, 4 MiB]`.
    - `planParts(5 GiB + 1, 8 MiB)` → throws 413.
    - `UPLOADS_CHUNK_MIB=4` → config validation error at boot.
    - `checkComplete(plan of 3, listed [1,3])` → `{missing:[2]}`.
    - `checkComplete` with part 1 at 7 MiB → `{badSize:[1]}`.
    - A `partNumbers` request containing `0` or `4` for a 3-part plan → 400.
  - **integration**:
    - These use Testcontainers Postgres plus MinIO or RustFS (the STACK-02 conformance store). Init a 20 MiB `application/pdf` session, presign parts 1–3, upload parts 1 and 2, then "drop". `GET /sessions/:id` → `uploadedParts [1,2]`. Presign part 3 again, upload it and confirm → `uploaded`. The object's sha256 equals the source's.
    - Confirm with part 2 never uploaded → 409 `MISSING_PARTS [2]`.
    - Revoke the user's `uploads.create` on the project after part 1. Requesting part 2 → 403.
    - Another user requesting parts on the session → 404. A `tenant-b` user → 404.
    - Set `expires_at` in the past, then request parts → 410 `SESSION_EXPIRED`. `abortExpiredMultipart(now)` → the status is `expired`, and `listMultipartUploads` for the prefix is empty.
    - `DELETE /sessions/:id` mid-upload → `aborted`, and the store has no in-progress upload.
  - **e2e**:
    - Playwright API project on the compose stack. A 64 MiB generated file uploaded in 8 parts. Abort the fetch during part 5, call `GET /sessions/:id`, then upload only the missing parts and confirm → `uploaded`. If UPLOADS-02 is merged, the session goes on to `released`.
