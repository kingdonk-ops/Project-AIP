# UPLOADS-01 — Upload sessions + presign to quarantine (tenant prefix, policy)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, STACK-02, TENANCY-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0004](../../docs/adr/0004-repository-layout.md), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (SSE-KMS with `tenant_id` encryption context)
4. Only for columns: [`data-model.md`](../../docs/blueprint/modules/uploads/data-model.md) (`upload_sessions`); for hardening intent: [`docs/reviews/01-security.md`](../../docs/reviews/01-security.md) risk #5

## Spec

Make a user-bound upload session the only way in. The server issues a short-lived presigned POST into a tenant-prefixed quarantine key, and the signed policy enforces size, content type and key, so the app is never in the byte path (tag: harden — replaces AIP's local-disk storage and its `/media/presign` flow).

- **files**:
  - db/migrations/<timestamp>_uploads_sessions.sql
  - apps/api/src/modules/uploads/manifest.json
  - apps/api/src/modules/uploads/module.ts
  - apps/api/src/modules/uploads/api.ts
  - apps/api/src/modules/uploads/schemas.ts
  - apps/api/src/modules/uploads/platform-limits.ts
  - apps/api/src/modules/uploads/sessions.service.ts
  - apps/api/src/modules/uploads/sessions.controller.ts
  - apps/api/src/modules/uploads/tests/sessions.spec.ts
  - apps/api/src/modules/uploads/tests/sessions.int.spec.ts
  - apps/api/src/platform/capabilities/object-store.ts (add `presignPost` and `head` to the STACK-02 interface and adapters only)
  - e2e/web/uploads-presign.spec.ts
- **steps**:
  - 1. Scaffold the `uploads` module. In its manifest, declare the permissions `uploads.create`, `uploads.view` and `uploads.admin`, and the events `upload.completed` and `upload.rejected` (emitted from UPLOADS-02).
  - 2. Migration: create `upload_sessions` with the data-model columns. Follow ADR 0002: UUIDv7 `id`, `mode` check `single|multipart`, nullable `s3_upload_id`, `quarantine_key`, and a `status` check of `requested|uploading|uploaded|scanning|validating|released|rejected|expired|aborted`.
    - `file_id` is a nullable uuid with **no FK yet**. UPLOADS-02 adds it with `stored_files`.
    - Add `unique (tenant_id, requested_by, client_request_id) where client_request_id is not null`.
    - Use FORCE RLS with the fail-closed policy and soft delete.
  - 3. `platform-limits.ts` holds the hard ceilings, which UPLOADS-05 moves to policy rows and caps at these values:
    - single-part max 100 MiB (larger sizes return 413 `USE_MULTIPART`)
    - declared-type allow-list: `image/jpeg`, `image/png`, `image/heic`, `image/webp`, `application/pdf`, `text/csv`, `text/plain`, and the xlsx and docx OOXML types
    - always denied: `image/svg+xml`, `text/html`, `application/xhtml+xml`, `application/javascript`, executables and archives
  - 4. `POST /api/v1/uploads/sessions {projectId, filename, declaredMime, sizeBytes, sha256?, clientRequestId?}`:
    - (a) `PolicyService.can(actor, 'uploads.create', {projectId})`, else 403.
    - (b) Validate type and size against the platform limits.
    - (c) Limit each user to 20 sessions in `requested|uploading`, else 429.
    - (d) Build the quarantine key with TENANCY-02 `s3Key(tenantId, 'quarantine', token)`, where `token` is 128 random bits (base64url). The key never contains the filename or the session id.
    - (e) `presignPost` with a 15-minute TTL and these conditions: the exact `key`, `content-length-range [1, sizeBytes]`, `Content-Type` equal to `declaredMime`, and `x-amz-server-side-encryption: aws:kms` with the tenant encryption context (the ADR 0006 local KMS stub in dev).
    - (f) Insert the session with status `requested` and `expires_at = now + 15 min`. Return `{sessionId, url, fields, expiresAt}`.

    A repeated `clientRequestId` returns the existing session, re-presigned if it is unexpired.
  - 5. `POST /api/v1/uploads/sessions/:id/confirm`:
    - Only the requester may call it. Another user gets 404, so session existence is never leaked.
    - It calls `ObjectStore.head(quarantineKey)`. A missing object gives 409 `OBJECT_MISSING`, and a size above the declared size gives 422.
    - It sets the status to `uploaded`. UPLOADS-02 hooks the scan enqueue onto this transition.
  - 6. `GET /api/v1/uploads/sessions/:id/status` returns `{status, rejectReason}` to the requester or a holder of `uploads.admin` in scope, and 404 to anyone else.
  - 7. `expireStaleSessions(now)` in `sessions.service.ts` marks `requested` sessions past `expires_at` as `expired`. UPLOADS-02 schedules it on the job runner.
  - 8. Export `UploadsApi.createSession` and `UploadsApi.getSessionStatus` from `api.ts`. `filename` is display-only and is never used for type, key or path.
- **acceptance**:
  - S3 itself (MinIO or RustFS in test) refuses an object that is larger than declared, has a different Content-Type, or goes to a different key.
  - Every quarantine key starts with `tenant/<tenantId>/quarantine/` and contains no user-supplied text.
  - Sessions are user-bound, tenant-isolated and expire.
  - No code path outside `modules/uploads` and `platform/capabilities` calls the object store for uploads. UPLOADS-02 adds the lint that enforces this.
- **tests**:
  - **unit**:
    - `declaredMime 'image/svg+xml'` → 415 `UNSUPPORTED_TYPE`. `sizeBytes 0` → 400. `sizeBytes 104857601` → 413 `USE_MULTIPART`.
    - `filename '../../etc/passwd.jpg'` → the session is created, and the key matches `^tenant/[0-9a-f-]{36}/quarantine/[A-Za-z0-9_-]{22}$`.
    - The presign conditions include `["content-length-range", 1, 2048]` for `sizeBytes 2048` and `["eq", "$Content-Type", "image/jpeg"]`.
  - **integration**:
    - These use Testcontainers Postgres plus the STACK-02 object-store container (RustFS or MinIO). As a `kaefer-demo` user with `uploads.create` on P1, create a 1,024-byte `image/jpeg` session, POST the form with a 1,024-byte file → 204, then confirm → `status: 'uploaded'`.
    - POST 2,048 bytes against a session declared at 1,024 → the store returns 400 or 403 (`EntityTooLarge` or a policy violation), and confirm → 409 `OBJECT_MISSING`.
    - POST with `Content-Type: text/html` against the jpeg session → rejected by the store.
    - Tamper with `key` in the form fields (`tenant/<A>/quarantine/other`) → rejected by the store.
    - User U2 in the same tenant confirms U1's session → 404. A `tenant-b` user GETs its status → 404.
    - A user without `uploads.create` on P2 creates a session for P2 → 403.
    - The same `clientRequestId` twice → the same `sessionId`, with 1 row.
    - `expireStaleSessions(now + 16 min)` → the session becomes `expired`, and confirm → 409.
  - **e2e**:
    - Playwright API project on the compose stack. The `kaefer-demo` user creates a session, uploads `e2e/fixtures/photo.jpg` via the presigned form and confirms → `GET status` returns `uploaded`. A `tenant-b` user replaying the same presigned fields with a changed key → rejected, and nothing is written outside `tenant/<A>/quarantine/<token>`.

## Carried forward from the STACK-02 review (PR #12, non-blocking)

- Validate presign expiry: `1 <= expires_s <= 604800`, with a lower policy cap for PUT (e.g. 900 s); add a unit test.
- Adapters should assert `key.startswith("tenant/")` at runtime (`ObjectKey` is only a `NewType`); `tenant_key()` should also reject control characters and `%`-encoded dots or slashes.
- `parse_adapter_config()`: NFKC-normalise keys; add `pass`, `pwd`, `auth`, `authorization`, `bearer`, `jwt`, `signature`, `sas`, `dsn`, `connection_string`, `cookie`; reject URL values with userinfo.
- Decide whether a KMS key is mandatory on RustFS/Coolify (needs KMS configured there; ADR 0006 covers LocalStack only). `presign_put` returns `PresignedRequest(method, url, headers)` because SSE-KMS headers are signed; the client must send them.
- Gotenberg: run with a Chromium deny/allow list and no route to internal services or metadata (HTML can fetch URLs); sanitise or template HTML in callers; `trust_env=False`; stream-limit the error body; consider a `max_bytes` on `get()`; fail when exactly one of the S3 access/secret keys is set.
