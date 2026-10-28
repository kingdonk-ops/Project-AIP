# UPLOADS-08 — Server-side file access in the uploads interface: store a generated file, read and attach a clean stored file

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`uploads`](../../docs/blueprint/modules/uploads/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | UPLOADS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/uploads/README.md`](../../docs/blueprint/modules/uploads/README.md)
3. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions, point 4)

## Spec

Add to the uploads published interface `store_generated_file` (a worker-made file such as a PDF becomes a clean `stored_files` row in the tenant prefix, with sha256 and size) and `open_stored_file` / `get_stored_file` (read a clean file, check it belongs to the caller's tenant) for report_engine, data_io and evidence links; the session status returns the stored `file_id` once clean, the file-type policy admits CSV and XLSX for imports, and `store_generated_file` takes an `idempotency_key` so a retried job does not leave an orphan object (tag: extend).

Spec written 2026-10-28 after UPLOADS-02 merged (PR #146). Consumers: REPORTS-02 (store a PDF, read snapshot
files), DATAIO-01 (read a CSV/XLSX upload; its tests use `store_generated_file` as the "put a clean stored file in
place" helper), INSPECTIONS-04 / ISSUES-04 / ELIGIBILITY-04 (check an attached file is clean and in the tenant).

- **files**:
  - apps/api/migrations/versions/202610281200_uploads_stored_files_generated.py
  - apps/api/aip/modules/uploads/tables.py
  - apps/api/aip/modules/uploads/repository.py
  - apps/api/aip/modules/uploads/stored_files.py (new)
  - apps/api/aip/modules/uploads/api.py
  - apps/api/aip/modules/uploads/schemas.py
  - apps/api/aip/modules/uploads/service.py
  - apps/api/aip/modules/uploads/pipeline/magic_bytes.py
  - apps/api/aip/modules/uploads/pipeline/runner.py
  - apps/api/aip/modules/uploads/tests/test_stored_files_unit.py (new)
  - apps/api/aip/modules/uploads/tests/test_stored_files_db.py (new)
  - apps/api/aip/modules/uploads/tests/test_scan_pipeline_db.py
  - packages/api-client/ (regenerated: `SessionStatus.fileId`)
- **steps**:
  - 1. **Migration** `202610281200_uploads_stored_files_generated` on `stored_files`:
    - add `source text NOT NULL DEFAULT 'upload'` with `CHECK (source IN ('upload', 'generated'))`;
      `filename text NULL` (display-only, like the session's `declared_filename`), `purpose text NULL`
      (`report`, `import`, `export`, ...), `idempotency_key text NULL`;
    - `project_id` and `uploaded_by` become nullable (a tenant-level report has no project; a system render has
      no user), with `CHECK (source = 'generated' OR (project_id IS NOT NULL AND uploaded_by IS NOT NULL))` so an
      upload keeps both. The ACCESS-03 project-scope policy already handles a NULL `project_id`
      (`access_project_visible(NULL)`: system and tenant-scoped principals only);
    - `CREATE UNIQUE INDEX uq_stored_files_tenant_id_idempotency_key ON stored_files (tenant_id, idempotency_key)
      WHERE idempotency_key IS NOT NULL`;
    - backfill `filename` of existing rows from their session's `declared_filename`.
  - 2. **Release** (`pipeline/runner.py`): the released row records `source = 'upload'` and the session's
    `declared_filename` as `filename`.
  - 3. **CSV/XLSX admitted for imports** (`pipeline/magic_bytes.py`): both were on the declared allow-list, but a
    clean CSV was stored with `detected_mime = 'text/plain'`, which an importer refuses. A text type that passes
    the UTF-8/NUL check now reports the declared type (`text/csv` or `text/plain`) as detected. XLSX passed the scan
    but was stored as its container `application/zip`; `stored_mime` (used by release) stores an OOXML file as its
    declared type while the ratio cap still sees the container. An integration test proves both end to end.
  - 4. **`stored_files.py`** (new, private) with `StoredFileRef` (frozen dataclass: `id`, `project_id | None`,
    `filename | None`, `content_type`, `size_bytes`, `sha256`, `source`, `purpose | None`, `created_at`) and:
    - `get_stored_file(conn, file_id) -> StoredFileRef | None`: a live, `clean` file visible on `conn` (tenant RLS
      plus the ACCESS-03 project scope of the connection's principal). Another tenant's, a deleted, or a not-yet-clean
      file → `None`, never an error, so a caller cannot tell them apart.
    - `open_stored_file(conn, file_id) -> bytes`: `get_stored_file`, then the object's bytes, re-hashed: a size or
      sha256 that differs from the row raises `StoredFileIntegrityError` (never hand out bytes the row does not
      describe). A missing/invisible/unclean file raises `StoredFileNotFoundError`.
    - `store_generated_file(conn, *, data, filename, content_type, purpose, idempotency_key, project_id=None,
      created_by=None) -> StoredFileRef`:
      - `content_type` must be on the platform allow-list and `data` must pass the magic-bytes check for it, and be
        1 byte to `SINGLE_PART_MAX_BYTES`; else `ValueError` (a worker bug, not user input). `filename` 1–255 chars,
        `purpose` and `idempotency_key` 1–200 chars.
      - The file id is `uuid5(namespace, "<tenant_id>:<idempotency_key>")` and the key is
        `tenant/<tenant>/files/<id>` (the one key builder), so a retried job writes the **same** object: a rolled-back
        attempt leaves nothing that the retry does not overwrite.
      - An existing row with that key: same sha256 → return it, no new object or row (idempotent replay); a different
        sha256 → `StoredFileConflictError`.
      - Otherwise put the object, then insert the row `source = 'generated'`, `scan_status = 'clean'`,
        `preview_status = 'none'` in the caller's transaction. No event (callers emit their own).
      - Runs with the caller's principal: a worker handler must already be a `system` principal (as the scan runner
        does); without one the project-scope RLS refuses the insert (fail closed).
  - 5. **`api.py`** exports `StoredFileRef`, `StoredFileNotFoundError`, `StoredFileIntegrityError`, `StoredFileConflictError`,
    `get_stored_file`, `open_stored_file`, `store_generated_file`.
  - 6. **Session status** (`schemas.SessionStatus`, `service.get_status`/`confirm`): add `file_id: UUID | None`
    (`fileId`), set once the session is `released`. Regenerate `packages/api-client` (`make generate-client`).
- **acceptance**:
  - report_engine can store a PDF and data_io can read a CSV/XLSX upload through `aip.modules.uploads.api` only.
  - A retried `store_generated_file` with the same key leaves one row and one object.
  - No caller can read a file of another tenant, a deleted file or one that is not clean.
  - `GET /uploads/sessions/{id}` returns `fileId` once released.
- **tests**:
  - **unit** (`test_stored_files_unit.py`):
    - `generated_file_id(t, "k")` is stable and differs for another tenant or key.
    - `store_generated_file` input checks: empty data, `image/svg+xml`, `%PDF` bytes declared `image/png`, NUL bytes
      as CSV, a 256-char filename → `ValueError`.
    - magic bytes: a UTF-8 CSV declared `text/csv` passes with `detected == 'text/csv'`; `stored_mime('application/zip',
      <xlsx>)` → the xlsx type.
  - **integration** (`test_stored_files_db.py`, Testcontainers Postgres + RustFS, tenants `kaefer-demo`, `tenant-b`):
    - As system on `kaefer-demo`: `store_generated_file(%PDF..., purpose='report', idempotency_key='report-render:1',
      project_id=P1)` → a `stored_files` row `source='generated'`, `scan_status='clean'`, 64-hex sha256 of the bytes,
      key under `tenant/<A>/files/`; `open_stored_file` returns the same bytes.
    - The same call again → the same id, 1 row. Different bytes with the same key → `StoredFileConflictError`.
    - A first attempt that rolls back after storing, then a retry with the same key → 1 row and the object at the
      row's key holds the retry's bytes (no orphan key).
    - `get_stored_file` from `tenant-b` → `None`; a quarantined row → `None`; a soft-deleted row → `None`;
      `open_stored_file` on each → `StoredFileNotFoundError`.
    - An object altered behind the row → `open_stored_file` raises `StoredFileIntegrityError`.
    - With no principal set, `store_generated_file` is refused by RLS.
    - In `test_scan_pipeline_db.py`: upload, scan and release a CSV and an XLSX → both `released`, `detected_mime` `text/csv` and the OOXML type,
      `filename` = the declared one, and `GET /uploads/sessions/{id}` → `fileId` equal to the row's id.
