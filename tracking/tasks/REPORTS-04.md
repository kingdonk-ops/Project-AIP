# REPORTS-04 — Report register with search and authorised download

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-03, REPORTS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`REPORTS-02.md`](REPORTS-02.md) (render jobs, `GET /reports/renders`, the pinned snapshot), [`UPLOADS-08.md`](UPLOADS-08.md) (`open_stored_file`), [`DESIGN-03.md`](DESIGN-03.md) (the register standard), [`PROJECTS-06.md`](PROJECTS-06.md) "As built" (the register pattern to copy)
3. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md) and [`routes.md`](../../docs/blueprint/modules/report_engine/routes.md) (`/reports/register` only)
4. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope), [0018](../../docs/adr/0018-module-groups-and-navigation.md) (Insight > Dashboards and reports), [0025](../../docs/adr/0025-time-and-timezones.md) (local time only at presentation), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 module decisions: sha256 only, files through uploads)
5. Code: `apps/api/aip/modules/report_engine/{routes,render_service,repository,schemas}.py`, `apps/api/aip/modules/uploads/stored_files.py`, `apps/web/src/features/projects/{ProjectsRegister,columns,search,nav}.tsx`, `e2e/web/projects.spec.ts`, `e2e/web/assets-live.spec.ts`

## Spec

Build the `/reports/register` page: a `RegisterTable` of the tenant's rendered reports (status, template, source
record, generated time) with search and a status filter, and an authorised PDF download that streams the stored
file through the API (tag: extend; AIP E7 S3 "report register", PRD §8).

The R1 register lists **render jobs** (REPORTS-02): published records, report numbers, revisions and supersession do
not exist yet (REPORTS-06). The download goes through the API and `aip.modules.uploads.api.open_stored_file`
(UPLOADS-08), never a presigned or raw storage URL, so every download is checked against `report.view` on the record's
project and RLS on the render job and the stored file.

Out of scope: report numbers, revisions, supersession and "Republish as superseding" (REPORTS-06); the PDF preview
drawer, "Download selected", "Add to data book" and the register CSV export (later rows; the API has no export yet);
client-variant download through the portal (PORTAL-05); expiring links and delivery receipts (publishing, later);
requesting a render from the page (REPORTS-03 renders on approval).

- **files**:
  - apps/api/migrations/versions/202610311500_report_engine_record_label.py
  - apps/api/aip/modules/report_engine/tables.py
  - apps/api/aip/modules/report_engine/providers/__init__.py
  - apps/api/aip/modules/report_engine/providers/project.py
  - apps/api/aip/modules/report_engine/repository.py
  - apps/api/aip/modules/report_engine/render_service.py
  - apps/api/aip/modules/report_engine/schemas.py
  - apps/api/aip/modules/report_engine/routes.py
  - apps/api/aip/modules/report_engine/events.py
  - apps/api/aip/modules/report_engine/manifest.toml
  - apps/api/aip/modules/report_engine/tests/test_register_download_db.py
  - apps/api/tests/access/idor_routes.toml
  - config/terms/en-AU/report_engine.json
  - db/schema.snapshot.sql
  - packages/api-client/** (regenerated)
  - apps/web/src/features/reports/{nav.ts,search.ts,columns.tsx,ReportsRegister.tsx,reports.css}
  - apps/web/src/features/reports/__tests__/reports.test.tsx
  - apps/web/src/routes/_app/reports/register.tsx
  - apps/web/src/router.ts
  - apps/web/src/features/shell/dev/dev-session-stub.ts
  - e2e/web/reports.spec.ts, e2e/web/reports-live.spec.ts
- **steps**:
  - 1. **Migration** `202610311500_report_engine_record_label.py`: `ALTER TABLE report_render_jobs ADD COLUMN
    record_label text NULL` with `CHECK (record_label IS NULL OR char_length(record_label) BETWEEN 1 AND 300)`. It is
    the source record's human label at request time (for a project, `"<code> <name>"`), kept on the job so the
    register can show and search it without reading snapshot bodies (up to 5 MB each). Rows from REPORTS-02 keep
    `NULL` (the page falls back to the record id). Add the column to `tables.py`.
  - 2. **Provider label.** `ReportSource` gains `label: str | None = None` (trimmed, cut to 300 characters by the
    service). The `project` provider sets `"<code> <name>"`. `request_render` stores it as `record_label`;
    `rerender` copies the first job's.
  - 3. **List filters** on `GET /api/v1/reports/renders` (still `report.view`, newest first, cursor paging, jobs on a
    project the caller may not view left out):
    - `status` (repeatable, each one of the four statuses; anything else → 422),
    - `q` (1–100 characters): case-insensitive substring of `record_label` or `template_key` (`%`, `_` and `\`
      escaped, so they match literally),
    - the existing `recordType` and `recordId`.
    Each item gains `recordLabel` and `templateNameKey` (the pinned template version's `name_key`, a terminology key,
    joined from `report_templates`; `null` if that row is gone). `GET /{id}` returns them too.
  - 4. **Download** `GET /api/v1/reports/renders/{render_job_id}/file` (operation `reports_renders_file`):
    - Another tenant's or a soft-deleted job → 404 `RENDER_JOB_NOT_FOUND` (RLS). No `report.view` on the job's
      project → 403 `FORBIDDEN`, nothing read.
    - Status not `succeeded` → 409 `REPORT_NOT_READY`.
    - `open_stored_file(conn, file_id)` on the request's `with_tenant` connection (clean files of this tenant only;
      it verifies size and sha256 against the stored row). `StoredFileNotFoundError` → 404 `REPORT_FILE_NOT_FOUND`.
      The bytes' sha256 must also equal the job's `pdf_sha256`, else 500 (`StoredFileIntegrityError`, logged with
      the job id): never serve bytes that are not the recorded report.
    - Emit `report.downloaded` v1 `{renderJobId, fileId, recordType, recordId, pdfSha256}` in the same transaction
      (the audit subscriber records who downloaded which report; ADR 0003 outbox).
    - 200 `application/pdf`, `Content-Disposition: attachment; filename="<template_key>-<variant>-<record_id>.pdf"`,
      `Content-Length`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`. The body is the bytes;
      no storage key or URL appears in any response.
    - Add it to `tests/access/idor_routes.toml` (`report_render_jobs`), so the generated IDOR test proves another
      tenant's id is a 404.
  - 5. **Terms** (`config/terms/en-AU/report_engine.json`, manifest `term_keys`): `report.error.REPORT_NOT_READY`,
    `report.error.REPORT_FILE_NOT_FOUND`, and the page's `reports.*` keys (nav, title, caption, search, status filter,
    column headers, download, empty/loading/error/paging, record type names).
  - 6. **Web page** `/reports/register` (`apps/web/src/features/reports/`, route `routes/_app/reports/register.tsx`),
    copying the projects register (PROJECTS-06):
    - Nav item `reports` in `insight` (ADR 0018: Insight > Dashboards and reports), permission `report.view`.
    - `RegisterTable` (`id="reports"`), adapter over the generated `useReportsRendersList`. URL state through
      `decodeRegisterQuery` / `encodeRegisterQuery`: `status` (quick select filter), `q`, `cursor`, `limit`, `cols`.
      No sortable columns (the API is newest first only).
    - Columns: Status (`StatusChip`: queued neutral/clock, running info/loader, succeeded success/check, failed
      danger/alert, label `report.render.status.<code>`), Template (`t(templateNameKey)` else `templateKey`, then
      `v<templateVersion>` and the variant term), Record (record type term and `recordLabel`, else the record id in
      mono), Generated (`renderedAt`, else `createdAt`, in the viewer's zone, `<time dateTime>`), Error (hidden by
      default: `report.error.<errorCode>`), Download.
    - Download: a plain same-origin `<a href="/api/v1/reports/renders/{id}/file" download>` (the session cookie
      authorises it; the browser never sees a storage URL) with an accessible name that names the record
      ("Download PDF for KF-01 …"); only for `succeeded` rows, others show nothing.
    - Empty state (no filter): "No reports have been generated yet." Error state shows the request id (DESIGN-03).
- **acceptance**:
  - A user with `report.view` sees the tenant's reports newest first, can search by record label or template and
    filter by status, and the URL reopens the same view.
  - Downloading a succeeded report gives the exact stored bytes (sha256 = `pdfSha256`) as an attachment; a queued
    or failed one is 409; another tenant's is 404; a user without `report.view` on the project is 403.
  - No API response or page contains a storage key or presigned URL.
  - Every download emits one `report.downloaded` event.
- **tests**:
  - **unit** (vitest, `apps/web/src/features/reports/__tests__/reports.test.tsx`, the projects register harness):
    rows render status chips, template name and version, record label (falling back to the id); a download link only
    on succeeded rows with the API href and a record-specific name; the status filter and search write the URL;
    the empty and error states; no nav item without `report.view`.
  - **integration** (`test_register_download_db.py`, pytest, real Postgres from Testcontainers, the RustFS object
    store fixture, no Gotenberg: a render is requested through the API and completed by storing a small PDF with
    `store_generated_file` and marking the job `succeeded`, as the REPORTS-02 handler does):
    - The list carries `recordLabel = "KF-01 Karratha compressor station"` and `templateNameKey`; `q=karratha`
      finds it, `q=zzz` does not, `q=%` matches nothing literal; `status=succeeded` and `status=queued` split the
      jobs; `status=bogus` → 422.
    - `GET .../file` on the succeeded job → 200 `application/pdf`, attachment filename, `no-store`, the exact bytes;
      1 `report.downloaded` event with the job id; the response headers and body hold no storage key.
    - On a queued job → 409 `REPORT_NOT_READY`. Dave (no `report.view`) → 403. Bob (tenant B) → 404
      `RENDER_JOB_NOT_FOUND`. A stored file whose bytes no longer match `pdf_sha256` → 500.
    - Add the file to the CI step that runs the REPORTS-02 render tests (it needs RustFS).
  - **e2e**:
    - `e2e/web/reports.spec.ts` (stub session, `page.route` fake list, like `projects.spec.ts`): the register shows
      the rows, the status filter and search land in the URL and a copied URL reopens the same view, the download
      link points at `/api/v1/reports/renders/<id>/file` and only on succeeded rows, the 390 px layout scrolls in its
      own region, and axe finds no serious or critical violation.
    - `e2e/web/reports-live.spec.ts` (`@skeleton`, compose stack with Gotenberg and `worker-pdf`): A requests a
      project-summary render through the API, waits for `succeeded`, finds it on `/reports/register` by searching the
      project code, clicks Download and gets a `%PDF` file whose sha256 is the row's `pdfSha256`; B gets a 404 for
      A's list item and download; axe on the register.
