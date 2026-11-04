# INSPECTIONS-14 — Photo and signature answers: upload through the pipeline, clean-file check on save

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- split from INSPECTIONS-04 (owner 2026-11-04) -->

| Field | Value |
|---|---|
| Module | [`inspections`](../../docs/blueprint/modules/inspections/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | INSPECTIONS-04, UPLOADS-08 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [INSPECTIONS-04](INSPECTIONS-04.md) (the answers tab this plugs into), [INSPECTIONS-02](INSPECTIONS-02.md)
   ("Out of scope": the deferred clean-file check), [FORMS-03](FORMS-03.md) (`MediaAdapter`, delivery note "Photo
   names"), [UPLOADS-01](UPLOADS-01.md) and [UPLOADS-08](UPLOADS-08.md) (sessions, scan, `get_stored_file`)
3. ADRs: [0036](../../docs/adr/0036-r1-module-decisions.md) (files only through uploads), [0010](../../docs/adr/0010-signoff-assurance.md)
   (a signature answer is evidence, not a sign-off)
4. Code: `apps/api/aip/modules/uploads/{routes,schemas,stored_files}.py`, `apps/api/aip/modules/inspections/responses.py`,
   `packages/form-renderer/src/adapters.ts`

## Spec

Let inspectors attach photos and capture signatures on an inspection: the web media adapter uploads through the
upload pipeline (session → PUT → confirm → wait for the scan) and the API only accepts a `photo` or `signature`
answer whose file ids name clean stored files of the tenant on the inspection's project (tag: extend; carries the
check INSPECTIONS-02 deferred).

**Out of scope:** camera capture on the field app and offline queues; image resizing or server thumbnails (the
browser shows the released file); the report's photo pages (REPORTS later rows).

- **files**:
  - apps/api/aip/modules/inspections/responses.py
  - apps/api/aip/modules/inspections/tests/test_media_answers_db.py
  - config/terms/en-AU/inspections.json
  - packages/form-renderer/src/adapters.ts, fields (optional `name(fileId)` on `MediaAdapter`)
  - apps/web/src/features/inspections/upload.ts (+ test): the first web client of the upload pipeline (kept in this
    module; moving it to a shared place is a later row once a second module needs it)
  - apps/web/src/features/inspections/adapters.ts, AnswersTab.tsx, SignaturePad.tsx
  - apps/web/src/features/inspections/__tests__/media.test.tsx
  - e2e/web/inspections-media-live.spec.ts
- **steps**:
  - 1. **Server check** in `responses.submit`: for each `photo` / `signature` answer, every file id must resolve with
    `aip.modules.uploads.api.get_stored_file` on the request's tenant connection, be `source = upload`, and have
    `project_id` equal to the inspection's project (when the inspection has one). Otherwise 422 `ANSWER_INVALID` with
    `{path, code: "FILE_NOT_AVAILABLE"}` and nothing written (the batch rule). Never reveal whether a file exists in
    another tenant (same code).
  - 2. **Upload helper** `apps/web/src/features/inspections/upload.ts`: `uploadFile(file, {projectId, purpose})` →
    `uploads_create_session` (with sha256 computed in the browser), POST the form to the returned `url` with
    `fields`, `uploads_confirm_session`, then poll `uploads_session_status` (1 s, then backing off, 60 s cap) until
    `released` (→ `fileId`) or `rejected` (→ `reject_reason` as a term). Abortable.
  - 3. **Media adapter** (`inspections/adapters.ts`): `pick` opens a file input (`accept="image/*"`) for photos or
    the `SignaturePad` dialog (canvas → PNG) for signatures, uploads, and resolves `{fileId, name}`;
    `thumbnailUrl(fileId)` returns a URL the tab prefetched with `uploads_file_url` for every file id in the current
    answers (null until it arrives; the renderer re-renders). Add `name(fileId)` to `MediaAdapter` (optional) so alt
    text uses the file name after reload. Progress and failures are announced politely.
  - 4. Terms: `inspection.error.file_not_available`, `inspection.media.*` (uploading, scanning, rejected, signature
    pad, clear, done).
- **acceptance**:
  - An inspector adds a photo and a signature on the answers tab; both survive reload with thumbnails.
  - An answer naming another tenant's, another project's, a pending or a rejected file is 422 and writes nothing.
  - No storage key appears in any answer; files only reach storage through upload sessions.
- **tests**:
  - **unit**: upload helper happy path, rejected scan, timeout and abort (fetch faked); adapter prefetches URLs and
    resolves names; signature pad produces a PNG and is keyboard reachable.
  - **integration** (`test_media_answers_db.py`, Testcontainers Postgres, RustFS fixture): a clean file of the
    project → 200; tenant B's file id, another project's file, a pending session's file and a generated file → 422
    `FILE_NOT_AVAILABLE`, 0 rows written.
  - **e2e**: `inspections-media-live.spec.ts` (`@skeleton`, compose stack with the scanner): A attaches a photo and
    signs, reloads and sees both; axe on the signature dialog; B's `GET /uploads/files/<id>/url` → 404.
