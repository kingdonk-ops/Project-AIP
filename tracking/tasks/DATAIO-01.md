# DATAIO-01 — Import jobs: upload, column mapping, dry run with row errors, async commit

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`data_io`](../../docs/blueprint/modules/data_io/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | ASSETS-01, OPS-17, UPLOADS-08 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/data_io/README.md`](../../docs/blueprint/modules/data_io/README.md) and, for columns only, [`data-model.md`](../../docs/blueprint/modules/data_io/data-model.md) (`import_jobs`, `import_row_errors`, `import_batches`, `import_batch_items`) and [`advice-security.md`](../../docs/blueprint/modules/data_io/advice-security.md)
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (`with_tenant`, raw-SQL Alembic, templates), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) and [0016](../../docs/adr/0016-job-runner-semantics.md) (Procrastinate jobs, the OPS-17 handler role), [0030](../../docs/adr/0030-outbox-dispatch-semantics.md) (outbox), [0033](../../docs/adr/0033-register-csv-exports.md) (CSV through `aip.platform.http.csv`), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 decisions: generic CSV/XLSX only, AIP format open)
4. The real code you build on: `apps/api/aip/modules/projects/` (module pattern), `apps/api/aip/modules/ops/api.py` (`register`, `enqueue`, `JobView`), [`OPS-17.md`](OPS-17.md) (handlers write tenant tables), [`UPLOADS-08.md`](UPLOADS-08.md) (`get_stored_file`, `open_stored_file`), `apps/api/aip/platform/http/csv.py`

> Scope. This row builds the generic import machinery: the job record, reading the uploaded file, column mapping,
> a dry run that writes nothing outside data_io, row errors, the async commit that records a batch, and the importer
> registry. It ships **no production importer**: the asset-tree importer is DATAIO-02, update-by-key is DATAIO-05, the
> AIP migration is DATAIO-04 (blocked on OPEN-QUESTIONS #54; do not design an AIP format here). Tenant export is not
> this module's R1 job (TENANCY-07). Batch rollback is DATAIO-02. Term-alias header matching is TERMS-06.

## Spec

Let a user import a generic CSV or XLSX file that went through the uploads pipeline: map its columns to an importer's fields, run an asynchronous dry run that reports row errors and writes no records, and commit it asynchronously as one recorded batch, with file, row and formula-injection limits enforced on the server (tag: extend).

- **files**:
  - apps/api/migrations/versions/<timestamp>_data_io_imports.py
  - apps/api/aip/modules/data_io/__init__.py
  - apps/api/aip/modules/data_io/manifest.toml
  - apps/api/aip/modules/data_io/tables.py
  - apps/api/aip/modules/data_io/schemas.py
  - apps/api/aip/modules/data_io/registry.py
  - apps/api/aip/modules/data_io/reader.py
  - apps/api/aip/modules/data_io/cells.py
  - apps/api/aip/modules/data_io/mapping.py
  - apps/api/aip/modules/data_io/repository.py
  - apps/api/aip/modules/data_io/service.py
  - apps/api/aip/modules/data_io/jobs.py
  - apps/api/aip/modules/data_io/policies.py
  - apps/api/aip/modules/data_io/events.py
  - apps/api/aip/modules/data_io/routes.py
  - apps/api/aip/modules/data_io/api.py
  - apps/api/aip/modules/data_io/tests/__init__.py
  - apps/api/aip/modules/data_io/tests/conftest.py
  - apps/api/aip/modules/data_io/tests/fake_importer.py
  - apps/api/aip/modules/data_io/tests/test_cells.py
  - apps/api/aip/modules/data_io/tests/test_reader.py
  - apps/api/aip/modules/data_io/tests/test_mapping.py
  - apps/api/aip/modules/data_io/tests/test_imports_db.py
  - apps/api/aip/modules/data_io/tests/fixtures/ (small `.csv` and `.xlsx` files, including a formula cell and an oversized zip)
  - apps/api/pyproject.toml (add `openpyxl` and `defusedxml`)
  - config/terms/en-AU/data_io.json
  - packages/api-client/openapi.json (regenerated)
- **steps**:
  - 1. Scaffold the module with `python tools/new_module.py data_io`. `manifest.toml`: `id = "data_io"`,
    `depends_on = ["uploads", "ops", "assets"]`, `permission_namespaces = ["import"]`, permissions `import.view`
    (see import jobs, their errors and batches) and `import.run` (create, map, dry-run, commit, cancel), events
    `import.committed` v1, term keys for every label in step 9. The importer's own target permission (for example
    `asset.create`) is checked as well (step 6); `import.run` alone never writes another module's records.
  - 2. Migration `<timestamp>_data_io_imports.py`, each table rendered from `db/templates/tenant_table.sql.tpl`
    (tenant_id, UUIDv7 id from the app, `created_at`/`updated_at`, `deleted_at`, FORCE ROW LEVEL SECURITY with the
    fail-closed policy, the template's `aip_app` grants; `aip_jobs` gets no grant because OPS-17 runs handlers on the
    path its ADR 0016 amendment chose):
    - create `import_jobs`: `project_id uuid NOT NULL` (upload sessions are project-scoped, so every R1 import is),
      `kind text` (the registry key; the data model's `target_entity`), `mode text` (`create` only in this row;
      `update_by_key` arrives with DATAIO-05, so a check constraint allows only `create` for now), `options jsonb`
      (importer options, default `{}`), `file_id uuid` (the uploads stored file; the data model's `document_id`),
      `file_name text`, `file_sha256 text` (64 hex), `content_type text`, `headers jsonb` (the detected header row),
      `mapping jsonb`, `status text` (`uploaded | validating | dry_run_ready | committing | committed | failed |
      cancelled`; `rolled_back` is added by DATAIO-02 without a migration because the check constraint lists it now),
      `failure_code text NULL`, `dry_run_no int NOT NULL DEFAULT 0`, `dry_run_result jsonb NULL`, `row_count int NULL`,
      `error_count int NULL`, `ops_job_id uuid NULL` (the `jobs` row of the running dry run or commit),
      `import_batch_id uuid NULL`, `requested_by uuid`, `committed_by uuid NULL`, `committed_at timestamptz NULL`,
      `sync_version int NOT NULL DEFAULT 1`; indexes `(tenant_id, status, created_at desc)` and
      `(tenant_id, requested_by)`.
    - create `import_row_errors`: `import_job_id` (FK to `import_jobs` with `tenant_id`), `dry_run_no int`,
      `row_number int` (1-based, the header is row 1, so the first data row is 2, as a spreadsheet shows it),
      `column_name text NULL`, `code text`, `message_key text`, `params jsonb`, `raw_value text NULL` (at most 200
      characters); index `(tenant_id, import_job_id, dry_run_no, row_number)`. Rows are never updated: a new dry run
      writes under a new `dry_run_no`, and reads use the job's current one.
    - create `import_batches`: `import_job_id`, `project_id`, `kind`, `created_count int`, `updated_count int`,
      `rollback_state text NOT NULL DEFAULT 'none'` (check: `none | blocked_downstream | rolled_back`),
      `rollback_block_reason jsonb NULL`, `rolled_back_by uuid NULL`, `rolled_back_at timestamptz NULL`,
      `sync_version int`; indexes `(tenant_id, created_at desc)`, `(tenant_id, rollback_state)`.
    - create `import_batch_items`: `import_batch_id` (FK with `tenant_id`), `entity text` (for example `asset`),
      `record_id uuid`, `asset_id uuid NULL` (plain uuid, no cross-module FK), `action text` (`created`),
      `before_values jsonb NULL`, `after_hash text`, `rolled_back boolean NOT NULL DEFAULT false`; indexes
      `(import_batch_id)`, `(tenant_id, entity, record_id)`, `(tenant_id, asset_id)`.
  - 3. `registry.py` — the importer registry other modules' importers plug into, exported from `api.py`:
    - `ImportField(key, term_key, type, required, max_length=None)` with `type` in `text | integer | decimal | date |
      boolean` (dates ISO `YYYY-MM-DD` or a real XLSX date cell; booleans `true/false/yes/no/1/0`, case-insensitive).
    - `Importer` protocol: `kind`, `target_permission`, `async fields(conn, options) -> list[ImportField]`,
      `options_model` (a strict Pydantic model, `extra="forbid"`), `async validate(conn, rows, ctx) ->
      ValidationResult(errors, preview)` and `async commit(conn, rows, ctx, recorder) -> CommitResult(created_count,
      updated_count)`. `rows` are `MappedRow(row_number, values)` with values already typed by step 5. `recorder`
      exposes `record(entity, record_id, *, action, asset_id=None, after_hash, before_values=None)`, which writes an
      `import_batch_items` row.
    - `register_importer(kind, importer)` (a duplicate kind raises `DuplicateImporter`), `get_importer(kind)`
      (unknown raises `UnknownImporter`), `registered_kinds()`. Importers are registered at import time of the
      module that owns them, like `aip.modules.ops.api.register`.
  - 4. `reader.py` — read the stored file through `aip.modules.uploads.api.get_stored_file(conn, file_id)` (clean
    files of the caller's tenant only) and stream it with `aip.modules.uploads.api.open_stored_file(file_id)`; never
    read the object store directly. Limits (module constants, also returned by `GET /imports/limits`):
    - `MAX_FILE_BYTES = 10 MiB` (checked against the stored size before opening and again while streaming),
      `MAX_ROWS = 10_000` data rows, `MAX_COLUMNS = 100`, `MAX_CELL_CHARS = 2_000`.
    - CSV (`text/csv`): UTF-8 with or without a BOM, comma-delimited, RFC 4180 quoting (`csv` module with
      `field_size_limit` set to `MAX_CELL_CHARS + 1`). Invalid UTF-8 → file error `ENCODING_UNSUPPORTED`.
    - XLSX (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`): before `openpyxl` opens it, sum the
      zip members' uncompressed sizes and refuse above 50 MiB or a compression ratio above 100 (`FILE_TOO_LARGE`, a
      zip-bomb guard); `defusedxml` installed so `openpyxl` parses with it; `load_workbook(read_only=True,
      data_only=False, keep_links=False)`; only the first worksheet; a file containing `xl/vbaProject.bin` →
      `UNSUPPORTED_FILE_TYPE`. Any other content type → `UNSUPPORTED_FILE_TYPE`.
    - The first non-empty row is the header row. Header cells are trimmed; an empty header with an empty column is
      dropped; two headers equal after trimming and case-folding → file error `DUPLICATE_HEADER`. Trailing empty
      rows are ignored. More than `MAX_ROWS` → `TOO_MANY_ROWS`; more than `MAX_COLUMNS` → `TOO_MANY_COLUMNS`.
    - File errors fail the whole run: the job goes to `failed` with `failure_code`; no row errors are written.
  - 5. `cells.py` — cell checks, applied to every mapped cell in the dry run and again in the commit:
    - **Formula injection: refused, not neutralised.** A text cell whose value, after stripping leading spaces,
      starts with `=`, `+`, `-`, `@`, a tab or a carriage return gives row error `formula_injection` and the row is
      not imported. An XLSX cell holding a formula (`cell.data_type == "f"`) gives the same error whatever the target
      type. The only exception: a field typed `integer` or `decimal` accepts a value matching
      `^[+-]?\d+(\.\d+)?$` (so `-12.5` is a negative number, not a formula). Refusing keeps the stored value
      exactly what the user typed and never silently changes data; the user fixes the cell and re-imports.
    - Over `MAX_CELL_CHARS`, or over the field's `max_length` → `too_long`. A required field empty → `required`.
      A value that does not parse to its type → `invalid_type` (with `params.expected`).
    - `raw_value` in `import_row_errors` holds the original text truncated to 200 characters. Every CSV that shows
      it (the error report, step 7) goes through `aip.platform.http.csv`, which prefixes a formula-looking cell with
      `'` (ADR 0033), so the report is safe to open in a spreadsheet.
  - 6. `mapping.py` and `service.py` (all writes in one `with_tenant` transaction per request):
    - `create_job(kind, project_id, file_id, options)`: unknown kind → 422 `UNKNOWN_IMPORTER`; options validated by
      the importer's `options_model` (unknown key → 422); the caller needs `import.run` and the importer's
      `target_permission` on `Resource(project_id=...)`; `get_stored_file` returning nothing → 422
      `FILE_NOT_AVAILABLE` (missing, another tenant's, or not yet clean); the stored file's project, when the
      `StoredFileRef` carries one, must equal `project_id` → else 422 `FILE_NOT_AVAILABLE`. Reads only the header row
      (step 4 limits apply), stores `headers`, `file_sha256`, `file_name`, `content_type`, status `uploaded`, and
      returns a suggested mapping: a header maps to a field when, after trimming, case-folding and collapsing spaces,
      underscores and hyphens, it equals the field key or the field's en-AU term text.
    - `set_mapping(job_id, mapping, expected_sync_version)`: `mapping` is `{header: field_key | null}`; every header
      must be one the file has; a field key not in the importer's fields → 422 `MAPPING_INVALID`; two headers to the
      same field → 422 `MAPPING_INVALID`; a required field unmapped → 422 `MAPPING_INCOMPLETE` listing the keys.
      Allowed in `uploaded`, `dry_run_ready` or `failed`; it resets the job to `uploaded` and clears
      `dry_run_result`, `row_count`, `error_count`. Written with `aip.platform.db.concurrency.update_with_version`
      (a stale `expectedSyncVersion` → 409).
    - `start_dry_run(job_id)`: needs a complete mapping; status `uploaded | dry_run_ready | failed` → `validating`,
      increments `dry_run_no`, and calls `aip.modules.ops.api.enqueue(conn, "data_io.dry_run", {"import_job_id":
      ...}, idempotency_key=f"data_io.dry_run:{job_id}:{dry_run_no}")` in the same transaction.
    - `commit(job_id, expected_sync_version)`: only from `dry_run_ready` with `error_count = 0` (else 409
      `IMPORT_HAS_ERRORS` or 409 `INVALID_IMPORT_STATE`); status → `committing`, enqueues `data_io.commit` with
      idempotency key `data_io.commit:{job_id}`. A partial import is not offered in R1.
    - `cancel(job_id)`: from `uploaded | dry_run_ready | failed` → `cancelled`; otherwise 409.
    - Another tenant's job id, or a missing one → 404 `IMPORT_NOT_FOUND`.
  - 7. `jobs.py` — two handlers registered with `aip.modules.ops.api.register(..., queue="import")`
    (`data_io.dry_run`: timeout 300 s, 3 attempts, `max_per_tenant=2`; `data_io.commit`: timeout 600 s, 1 attempt).
    Each runs in the job's tenant transaction (OPS-17) and is idempotent: it reloads the import job and returns at
    once unless the status is still `validating` (dry run, same `dry_run_no`) or `committing` (commit).
    - Dry run: re-check that the file's sha256 equals `file_sha256` (else `failed`, `FILE_CHANGED`); read every row
      (step 4), type and check cells (step 5), then call `importer.validate` inside a SAVEPOINT
      (`conn.begin_nested()`) that is **always rolled back**, so nothing an importer writes there survives. Then write
      the row errors (at most 1,000 rows per run; `error_count` holds the true total), `row_count`, `dry_run_result`
      (`{counts: {rows, valid, invalid}, errorCodes: {code: n}, preview: <importer preview>}`) and status
      `dry_run_ready`. Only `import_jobs` and `import_row_errors` change.
    - Commit: re-read and re-check the file and cells exactly as the dry run did; if any row now fails, the job goes
      to `failed` with `failure_code = "ROWS_CHANGED_SINCE_DRY_RUN"`, its row errors written under a new
      `dry_run_no`, and nothing else is kept. Otherwise create the `import_batches` row, call `importer.commit` with a
      recorder bound to it, set `import_batch_id`, `committed_by`, `committed_at`, `created_count`/`updated_count`
      and status `committed`, and `emit(conn, "import.committed", 1, ...)` with payload
      `{importJobId, importBatchId, kind, projectId, createdCount, updatedCount}` — all in the handler's one
      transaction, so an importer failure leaves no records, no batch and no event. A raised error marks the job
      `failed` with `failure_code = "COMMIT_FAILED"` in a separate transaction (the ops runner records the job error).
  - 8. `routes.py` under `/api/v1/imports` (deny by default, every route with `requires(...)` from
    `aip.platform.access.dependencies`; strict request models, unknown keys → 400):
    - `GET /importers` (`import.view`) → the kinds the caller may run (has `import.run` and the target permission),
      each with `fields` (`key`, `termKey`, `type`, `required`) and its options schema.
    - `GET /importers/{kind}/template.csv` (`import.view`) → a header-only CSV of the field keys, written with
      `aip.platform.http.csv.csv_header` (options passed as query parameters when fields depend on them).
    - `GET /limits` → the step 4 limits.
    - `POST /` `{kind, projectId, fileId, options?}` (`import.run`) → 201 with the job and `suggestedMapping`.
    - `GET /` (`import.view`) → the history register: cursor-paged, newest first, filters `status`, `kind`,
      `projectId`, `requestedBy`; `GET /{id}` → the job with counts, `dryRunResult`, `failureCode`, `opsJobId`.
    - `PUT /{id}/mapping`, `POST /{id}/dry-run` (202), `POST /{id}/commit` (202), `POST /{id}/cancel` (`import.run`).
    - `GET /{id}/errors?cursor&limit` and `GET /{id}/errors.csv` (`import.view`) → the current run's row errors
      (`rowNumber`, `column`, `code`, `messageKey`, `params`, `rawValue`); the CSV is streamed with `csv_header` and
      `csv_row` and its headers are the API field names (ADR 0033).
    - The route resource is `Resource(project_id=job.project_id)`, so a project-scoped grant works.
  - 9. Term keys in `config/terms/en-AU/data_io.json`: one `data_io.error.<code>` per row error and file error code
    above, `data_io.status.<status>` per status, and the field and option labels the importers reference. API
    errors carry codes, never English.
  - 10. `api.py` exports `register_importer`, `get_importer`, `registered_kinds`, `Importer`, `ImportField`,
    `MappedRow`, `ValidationResult`, `CommitResult`, `BatchRecorder`, `ImportContext` (`actor_id`, `project_id`,
    `options`, `import_job_id`). Regenerate the OpenAPI client.
- **acceptance**:
  - A clean CSV or XLSX of the caller's tenant goes `uploaded → validating → dry_run_ready → committing → committed`
    through the API and two Procrastinate jobs on the `import` queue; the commit writes one `import_batches` row, one
    `import_batch_items` row per created record and one `import.committed` event in the same transaction.
  - A dry run changes no table outside `import_jobs` and `import_row_errors`, even when an importer writes during
    `validate`.
  - A cell starting with `=`, `+`, `-`, `@`, tab or CR, or any XLSX formula cell, is refused as `formula_injection`
    (numbers such as `-12.5` in numeric fields excepted), and the error report CSV neutralises it with a leading `'`.
  - Files over 10 MiB, over 10,000 rows or 100 columns, zip bombs, macro workbooks and other content types fail with
    their codes before any row is processed.
  - Commit is refused while the current dry run has errors; there is no partial import.
  - Every route is permission-checked; another tenant's job, file or error list gives 404.
- **tests**:
  - **unit** (`test_cells.py`, `test_reader.py`, `test_mapping.py`):
    - `check_cell("=HYPERLINK(\"http://x\")", text)` → `formula_injection`; `"+61 400 000 000"` as `text` →
      `formula_injection`; `"  @SUM(A1)"` → `formula_injection`; `"\t=1"` → `formula_injection`; `"Tank =A"` → ok.
    - `check_cell("-12.5", decimal)` → ok, value `Decimal("-12.5")`; `check_cell("-12.5", text)` →
      `formula_injection`; `check_cell("-1e5", decimal)` → `formula_injection`.
    - `check_cell("2026-02-30", date)` → `invalid_type`; `"Yes"` as `boolean` → `True`; 2,001 characters → `too_long`.
    - XLSX fixture with `B3` holding `=1+1` (cached value 2) → one row error, row 3, column `B` header,
      `formula_injection`.
    - CSV with a BOM and CRLF → headers without the BOM; invalid UTF-8 bytes → `ENCODING_UNSUPPORTED`.
    - 10,001 data rows → `TOO_MANY_ROWS`; 101 columns → `TOO_MANY_COLUMNS`; headers `Tag` and ` tag ` →
      `DUPLICATE_HEADER`; a zip whose one member inflates to 60 MiB → `FILE_TOO_LARGE`; a workbook with
      `xl/vbaProject.bin` → `UNSUPPORTED_FILE_TYPE`.
    - Suggested mapping: headers `[" Tag_Number ", "NAME", "Notes"]` against fields `tag_number`, `name` →
      `{" Tag_Number ": "tag_number", "NAME": "name", "Notes": null}`.
    - `register_importer("fake", ...)` twice → `DuplicateImporter`; `get_importer("nope")` → `UnknownImporter`.
    - Error report CSV for a row error with `raw_value = "=cmd|' /C calc'!A0"` → the cell is written as
      `"'=cmd|' /C calc'!A0"` quoted per RFC 4180.
  - **integration** (`test_imports_db.py`, testcontainers-python Postgres, the TESTING-01 tenants `kaefer-demo` and
    `tenant-b`, UPLOADS-08's test helper to put a clean stored file in place, the ops runner driven in-process; the
    `fake` importer in `tests/fake_importer.py` has fields `tag_number` (text, required), `name` (text, required),
    `rating` (decimal), target permission `asset.create`, and its `commit` calls
    `aip.modules.assets.api.AssetsApi.create_asset` for each row at the root):
    - A `kaefer-demo` user with `import.run` and `asset.create` POSTs `/api/v1/imports` with a 3-row CSV → 201,
      status `uploaded`, `headers = ["Tag Number","Name","Rating"]`; PUT mapping; POST dry-run → 202; after the
      runner: status `dry_run_ready`, `rowCount = 3`, `errorCount = 0`, and `SELECT count(*) FROM assets` is unchanged.
    - POST commit → 202; after the runner: status `committed`; 3 `assets` rows; 1 `import_batches` row with
      `created_count = 3`; 3 `import_batch_items` rows with `entity = 'asset'` and a 64-hex `after_hash`; 1
      `domain_events` row `import.committed` v1 with `createdCount = 3`.
    - A 5-row CSV where row 4 has `Name = "=2+3"` and row 6 has `Rating = "abc"` → `errorCount = 2`; `GET /errors`
      returns `[{rowNumber: 4, code: "formula_injection"}, {rowNumber: 6, code: "invalid_type"}]`; POST commit → 409
      `IMPORT_HAS_ERRORS` and `SELECT count(*) FROM import_batches` is 0.
    - The fake importer's `validate` inserts an `assets` row through `create_asset` → after the dry run that row
      does not exist (the savepoint rolled back).
    - Make `create_asset` raise on the 3rd row during commit → job `failed` with `COMMIT_FAILED`; 0 new `assets`
      rows, 0 `import_batches` rows, 0 `import.committed` events.
    - Change the file's bytes in the test store after the dry run → commit gives `failed`, `FILE_CHANGED`.
    - Run the dry-run handler twice for the same `dry_run_no` → the second returns without writing; the
      `import_row_errors` count is unchanged.
    - PUT mapping with two headers on `name` → 422 `MAPPING_INVALID`; without `tag_number` → 422
      `MAPPING_INCOMPLETE`; with `expectedSyncVersion` one behind → 409.
    - A user with `import.run` but without `asset.create` → POST `/imports` 403 and `GET /importers` omits `fake`.
      A user with neither → `GET /imports` 403.
    - A `tenant-b` user: `GET /api/v1/imports/{kaefer job id}` → 404; `GET .../errors` → 404; POST `/imports` with
      the `kaefer-demo` `fileId` → 422 `FILE_NOT_AVAILABLE`.
    - A file still `pending` scan → 422 `FILE_NOT_AVAILABLE`.
    - POST `/imports` with `{"kind":"fake","projectId":...,"fileId":...,"status":"committed"}` → 400.
    - `GET /importers/fake/template.csv` → body is the BOM plus `tag_number,name,rating\r\n`.
  - **e2e**:
    - API-only task: covered by the Postgres integration tests above (the jobs run in-process on the real roles).
      The browser journey, its cross-tenant check and axe run land with the wizard pages in DATAIO-03.
