# REPORTS-02 — Render job: Gotenberg PDF in the worker, stored as an uploads stored_files row with a pinned data snapshot

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | OPS-17, REPORTS-01, UPLOADS-08 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`REPORTS-01.md`](REPORTS-01.md) (the render contract this task calls), [`UPLOADS-08.md`](UPLOADS-08.md) (`store_generated_file`, `get_stored_file`, `open_stored_file`), [`OPS-17.md`](OPS-17.md) (which role a job handler writes tenant tables with)
3. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md), and for columns only [`data-model.md`](../../docs/blueprint/modules/report_engine/data-model.md) (`report_render_jobs`, `report_data_snapshots`)
4. [`advice-security.md`](../../docs/blueprint/modules/report_engine/advice-security.md) (render with no network and no JavaScript)
5. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (append-only grants), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (Procrastinate, atomic enqueue, outbox), [0016](../../docs/adr/0016-job-runner-semantics.md) (handler contract, idempotent handlers), [0025](../../docs/adr/0025-time-and-timezones.md) (local time only at presentation), [0030](../../docs/adr/0030-outbox-dispatch-semantics.md), [0036](../../docs/adr/0036-r1-module-decisions.md) (store a sha256 only; sealing is open, OPEN-QUESTIONS #47–#49)
6. Code: `apps/api/aip/platform/capabilities/protocols.py` (`PdfRenderer`), `adapters/gotenberg.py` (`GotenbergPdfRenderer`, `CONVERT_HTML_PATH`), `apps/api/aip/modules/ops/api.py` (`register`, `enqueue`, `JobView`), `apps/api/aip/modules/ops/registry.py` (handler contract), `apps/api/tests/platform/capabilities/test_gotenberg.py`, the `gotenberg` and `worker` services in `infra/docker-compose.yml`

## Spec

Render a report as a background job: freeze the record's data into an append-only snapshot in the request's transaction, render the pinned template version through the REPORTS-01 contract and the Gotenberg adapter on a network-isolated, JavaScript-free Chromium, store the PDF with `aip.modules.uploads.api.store_generated_file`, and record its sha256 against the template version and snapshot hash (tag: extend).

Out of scope: published records, numbering and supersession (REPORTS-06), the register page and authorised download
(REPORTS-04), the inspection data and auto-render on approval (REPORTS-03), sealing, external signing and immutable
storage (OPEN-QUESTIONS #47–#49; R1 records a sha256 only, ADR 0036 §5).

- **files**:
  - apps/api/aip/modules/report_engine/manifest.toml
  - apps/api/aip/modules/report_engine/api.py
  - apps/api/aip/modules/report_engine/tables.py
  - apps/api/aip/modules/report_engine/schemas.py
  - apps/api/aip/modules/report_engine/repository.py
  - apps/api/aip/modules/report_engine/render_service.py
  - apps/api/aip/modules/report_engine/snapshots.py
  - apps/api/aip/modules/report_engine/render.py
  - apps/api/aip/modules/report_engine/providers/__init__.py
  - apps/api/aip/modules/report_engine/providers/project.py
  - apps/api/aip/modules/report_engine/jobs.py
  - apps/api/aip/modules/report_engine/events.py
  - apps/api/aip/modules/report_engine/routes.py
  - apps/api/aip/modules/report_engine/tests/test_snapshots.py
  - apps/api/aip/modules/report_engine/tests/test_render_handler.py
  - apps/api/aip/modules/report_engine/tests/test_render_jobs_db.py
  - apps/api/aip/modules/report_engine/tests/test_render_pdf.py
  - apps/api/migrations/versions/<timestamp>_report_engine_render_jobs.py
  - apps/api/aip/platform/capabilities/protocols.py
  - apps/api/aip/platform/capabilities/adapters/gotenberg.py
  - apps/api/aip/platform/capabilities/__init__.py
  - apps/api/tests/platform/capabilities/test_gotenberg.py
  - config/terms/en-AU/report_engine.json
  - infra/docker-compose.yml
  - infra/coolify/docker-compose.coolify.yml
- **steps**:
  - 1. **Migration** `<timestamp>_report_engine_render_jobs.py`:
    - Create `report_data_snapshots`, append-only and hand-written like `workflow_decision_history`
      (`202610181200_approvals_decision_history.py`): `id uuid PK`, `tenant_id uuid NOT NULL REFERENCES tenants`,
      `record_type text`, `record_id uuid`, `record_version integer NULL`, `project_id uuid NULL`, `schema_version
      integer NOT NULL DEFAULT 1`, `data jsonb NOT NULL`, `data_hash text CHECK (data_hash ~ '^[0-9a-f]{64}$')`,
      `size_bytes integer CHECK (size_bytes <= 5242880)`, `created_by uuid NULL`, `created_at timestamptz NOT NULL
      DEFAULT now()`. No `updated_at` or `deleted_at`. `UNIQUE (tenant_id, record_type, record_id, data_hash)` (the
      same data is snapshotted once), `UNIQUE (id, tenant_id)` for the FK below, index `(tenant_id, record_type,
      record_id, created_at DESC)`. FORCE RLS with the fail-closed `tenant_isolation` policy;
      `REVOKE UPDATE, DELETE, TRUNCATE` from `aip_app`, `aip_jobs` and `aip_readonly`; `GRANT SELECT, INSERT` to
      `aip_app` and `SELECT` to `aip_readonly`. It is not range-partitioned: one row per distinct render input is low
      volume, and a partitioned key would stop render jobs referencing it (the ADR 0031 reasoning for `audit_log`).
    - Create `report_render_jobs` from `render_template("tenant_table", table="report_render_jobs", columns=...)`:
      `template_id uuid` (the pinned version; FK `(template_id, tenant_id)` → `report_templates (id, tenant_id)`, so
      add `UNIQUE (id, tenant_id)` to `report_templates` here), `template_key text`, `template_version integer`,
      `variant text`, `record_type text`, `record_id uuid`, `project_id uuid NULL`, `snapshot_id uuid` (FK
      `(snapshot_id, tenant_id)` → `report_data_snapshots`), `data_hash text`, `status text CHECK (status IN
      ('queued','running','succeeded','failed'))`, `ops_job_id uuid NULL` (the OPS-01 `jobs` row), `idempotency_key
      text NULL` (`UNIQUE (tenant_id, idempotency_key)`), `trigger_event_id uuid NULL`, `requested_by uuid NULL`
      (NULL for a system request), `html_sha256 text NULL`, `file_id uuid NULL` (the uploads stored file; no FK
      across modules), `pdf_sha256 text NULL CHECK (pdf_sha256 IS NULL OR pdf_sha256 ~ '^[0-9a-f]{64}$')`,
      `pdf_size_bytes bigint NULL`, `error_code text NULL`, `rendered_at timestamptz NULL`, and
      `CHECK (status <> 'succeeded' OR (file_id IS NOT NULL AND pdf_sha256 IS NOT NULL))`. Indexes `(tenant_id,
      status, created_at)` and `(tenant_id, record_type, record_id, created_at DESC)`.
    - Grants for the handler follow OPS-17's ADR 0016 amendment. With option (a) (handlers on the `aip_app` engine)
      nothing more is needed. With option (b), grant `aip_jobs` `SELECT, UPDATE` on `report_render_jobs` and
      `SELECT` on `report_templates` and `report_data_snapshots`, and nothing else.
  - 2. **Manifest and events.** Add permissions `report.view` ("View rendered reports") and `report.create`
    ("Request a report render"), so ADR 0027 gives `create` to every role with `create` or higher on the report
    engine row. Declare events `report.render_succeeded` v1 (`{renderJobId, templateKey, templateVersion, variant,
    recordType, recordId, dataHash, fileId, pdfSha256}`) and `report.render_failed` v1 (`{renderJobId, templateKey,
    variant, recordType, recordId, errorCode}`), registered in `events.py`.
  - 3. **Data providers** (`providers/__init__.py`, internal to report_engine): `register_provider(record_type,
    provider, *, view_permission)`. A provider is `async (conn, record_id, *, context) -> ReportSource` (`context` is trigger data, `{}` for a manual render) with `project_id`,
    `record_version`, `data` (a JSON dict), `files` (a list of `{fileId, role}` the template may show) and
    `time_zone_hint`. It raises `RecordNotFound` for a missing record or another tenant's id (RLS). `providers/
    project.py` registers `project` (view permission `project.view`): `aip.modules.projects.api.ProjectsApi
    .get_project(conn, project_id)`, giving `{project: {id, code, name, status, timezone, region, createdAt}}`.
    REPORTS-03 adds `inspection`.
  - 4. **Snapshots** (`snapshots.py`): `build_snapshot(conn, template, source, *, locale='en-AU')`.
    - `labels` = `aip.modules.terms.api.bulk_resolve` of the template's `termKeys` for the tenant and project.
    - `unitSystem` = `aip.modules.terms.api.display_system(conn, tenant_id, project_id)`.
    - `timeZone` = the project's `timezone`, else `UTC` (ADR 0025; zones are IANA ids).
    - `files` = each `source.files` entry with `sha256`, `sizeBytes` and `contentType` from
      `aip.modules.uploads.api.get_stored_file(conn, file_id)` (clean files of this tenant only; anything else →
      `RecordNotFound`).
    - The snapshot body is `{schemaVersion: 1, recordType, recordId, recordVersion, record: source.data, labels,
      locale, timeZone, unitSystem, files}`. `data_hash` = sha256 (hex) of its RFC 8785 canonical JSON (`rfc8785`). No
      clock value goes into the body, so unchanged data gives the same hash. A body over 5 MB → 422
      `SNAPSHOT_TOO_LARGE`.
    - Insert with `ON CONFLICT (tenant_id, record_type, record_id, data_hash) DO NOTHING`, then select, so a repeat
      reuses the existing row.
  - 5. **Request** (`render_service.py`, `RenderService.request_render(conn, *, template_key, record_type,
    record_id, variant, requested_by, idempotency_key=None, trigger_event_id=None, context=None) -> RenderJobView`), in the
    caller's `with_tenant` transaction:
    - (a) A known `idempotency_key` returns the existing job (the `UNIQUE` index settles a race: on a unique
      violation, re-read and return).
    - (b) `ReportTemplatesApi.get_published(conn, template_key, variant)`; none → 404 `TEMPLATE_NOT_FOUND`. The
      template's `record_type` must equal `record_type`, else 422 `TEMPLATE_RECORD_TYPE_MISMATCH`.
    - (c) Look up the provider; none → 422 `UNKNOWN_RECORD_TYPE`. Call it; `RecordNotFound` → 404
      `RECORD_NOT_FOUND`.
    - (d) Build the snapshot (step 4), insert the `report_render_jobs` row (`queued`, pinned `template_id` and
      `template_version`, `snapshot_id`, `data_hash`), then call `aip.modules.ops.api.enqueue(conn,
      "report_engine.render", {"renderJobId": "<id>"}, idempotency_key="report-render:<id>")` and store the returned
      `JobView.id` as `ops_job_id`. All of it is one transaction: a rollback leaves no snapshot, no render job, no
      `jobs` row and no queue row (ADR 0003).
    - `rerender(conn, actor, render_job_id)` creates a new render job with the same `template_id` and `snapshot_id`
      (re-render with the pinned version, never the latest), even if that template is now `retired`.
  - 6. **Routes** under `/api/v1/reports/renders`, `require_active_tenant`, strict bodies (unknown key → 422):
    - `POST ""` (`report.create`), body `{templateKey, variant, recordType, recordId}`, optional `Idempotency-Key`
      header (≤ 128 characters). After the provider has resolved the record, the service checks `report.create` and
      the provider's `view_permission` with `PolicyService.can(principal, code, Resource(project_id=...))`; a deny is
      403 with nothing written. Answers 202 `{id, status: 'queued', templateId, templateVersion, dataHash}`.
    - `GET "/{render_job_id}"` (`report.view`, the record's project as resource): status, `fileId`, `pdfSha256`,
      `pdfSizeBytes`, `htmlSha256`, `errorCode`, `renderedAt` (UTC, `Z`). Another tenant's id → 404
      `RENDER_JOB_NOT_FOUND`.
    - `GET ""` (`report.view`), filters `recordType` and `recordId`, cursor paging (limit 1–200), newest first.
    - `POST "/{render_job_id}/rerender"` (`report.create`) → 202 with the new job.
  - 7. **Page options in the Gotenberg adapter** (platform change; existing callers are unchanged). Add
    `PageOptions(paper_width_mm, paper_height_mm, landscape, margin_top_mm, margin_right_mm, margin_bottom_mm,
    margin_left_mm)` to `protocols.py` and export it from `aip.platform.capabilities`. `PdfRenderer.render_html(html,
    *, assets=None, page: PageOptions | None = None)`. `GotenbergPdfRenderer` sends the multipart form fields
    `paperWidth`, `paperHeight` and `marginTop`/`marginRight`/`marginBottom`/`marginLeft` (as `"210mm"` strings),
    `landscape` (`"true"`/`"false"`), `printBackground=true` and `preferCssPageSize=false` when `page` is given, and
    none of them when it is `None` (today's request, so `test_render_store_and_download_report` is unchanged). A4 is
    210 × 297 mm and A3 is 297 × 420 mm; `PageSpec` from REPORTS-01 maps to it in report_engine.
  - 8. **Sandboxed Gotenberg** (`infra/docker-compose.yml`, `infra/coolify/docker-compose.coolify.yml`):
    - Give the `gotenberg` service (`gotenberg/gotenberg:8.37.0`) a `command` with
      `--chromium-disable-javascript=true`, `--chromium-allow-list=^file:///tmp/.*` (Chromium may load only the
      request's own files), `--api-disable-download-from=true` and `--webhook-disable=true`. Check each flag against
      `docker run --rm gotenberg/gotenberg:8.37.0 gotenberg --help` first. If the pinned version spells one
      differently, use its spelling and say so in the PR; never drop a control silently.
    - Add a `worker-pdf` service: the same image and hardening as `worker`, `command: ["python", "-m", "aip.worker",
      "--queues", "pdf"]`, depending on `gotenberg` being healthy. The `pdf` queue already exists in
      `aip.platform.jobs.app.QUEUES`.
    - On Coolify, put `gotenberg` on its own `render` network with `internal: true`, joined only by `worker-pdf`
      (no egress, no route to Postgres, RustFS or Keycloak). The dev compose keeps the loopback port
      `127.0.0.1:3000` that the CI Gotenberg tests use; the Chromium flags are the control there.
  - 9. **Job handler** (`jobs.py`): `aip.modules.ops.api.register("report_engine.render", render_report,
    queue="pdf", timeout_s=120, max_attempts=3, max_per_tenant=2)`. `render_report(conn, job)` runs on the
    connection OPS-17 provides (bound to the job's tenant) and is idempotent on the render job id:
    - (a) `SELECT ... FOR UPDATE` the render job named by `job.payload["renderJobId"]`. Already `succeeded` → return
      its `file_id` as `result_ref` and do nothing else. Already `failed` → return.
    - (b) Set `running`. Load the pinned template row (by `template_id`, never the latest) and the snapshot.
    - (c) Call `render_html` (REPORTS-01) with `data = {**snapshot.record, "report": {"renderJobId", "issuedAt":
      <render job created_at>, "templateVersion", "dataHash"}}` and the snapshot's labels, locale, zone and unit
      system. Snapshot files are added as assets named `file-<fileId>.<ext>`: read each with
      `aip.modules.uploads.api.open_stored_file`, and if its sha256 differs from the snapshot's → fail
      `SOURCE_FILE_CHANGED`. Pass them to `render_html` as a new `extra_assets` argument, so the `asset()` filter
      and the HTML policy accept those names as declared assets. Record `html_sha256`.
    - (d) `get_pdf_renderer().render_html(html, assets=..., page=PageOptions(...))`.
    - (e) `ref = aip.modules.uploads.api.store_generated_file(conn, data=pdf,
      filename="<template_key>-<variant>-<record_id>.pdf", content_type="application/pdf", purpose="report",
      idempotency_key="report-render:<render_job_id>")`. `ref.sha256` must equal the sha256 computed here, else raise
      (never record a hash of bytes that were not stored).
    - (f) Set `succeeded` with `file_id`, `pdf_sha256`, `pdf_size_bytes` and `rendered_at`, and `emit(conn,
      "report.render_succeeded", 1, ...)` in the same transaction. Return `str(ref.id)`.
    - Failures:
      - `RenderContractError` and `SOURCE_FILE_CHANGED` → `failed` with `error_code` (`RENDER_CONTRACT_VIOLATION`
        or `SOURCE_FILE_CHANGED`), emit `report.render_failed`, return without raising (a retry cannot fix them).
      - `RenderTooLargeError` → `failed` `PDF_TOO_LARGE`, the same way.
      - `RenderTimeoutError` and `RenderError` → re-raise so Procrastinate retries. On the last try
        (`job.attempts >= 3`) set `failed` `RENDER_UNAVAILABLE` and emit `report.render_failed` instead.
      - Logs carry the render job id and error code, never snapshot data.
  - 10. **Published interface** (`api.py`): `ReportsApi.request_render(conn, *, template_key, record_type, record_id,
    variant, requested_by=None, idempotency_key=None, trigger_event_id=None, context=None) -> RenderJobView` (a system call with no
    policy check, for report_engine's own subscribers and later callers that have already authorised the user) and
    `ReportsApi.get_render_job(conn, render_job_id) -> RenderJobView | None`.
  - 11. **Terms**: add `report.render.status.<code>` for the four statuses and `report.error.<code>` for every new
    error code to `config/terms/en-AU/report_engine.json`.
- **acceptance**:
  - A render request commits the snapshot, the render job, the `jobs` row and the queue row together, or none of them.
  - The `pdf` worker renders with the template version that was current at request time, even after a newer version
    is published. Re-render reuses the same template version and snapshot and produces the same `html_sha256`.
  - Every succeeded render has a stored file whose bytes hash to the recorded `pdf_sha256`.
  - A landscape template gives landscape pages.
  - With the compose Gotenberg, Chromium runs no JavaScript and loads nothing but the request's own files.
  - Snapshots cannot be changed or deleted by any runtime role.
- **tests**:
  - **unit**:
    - These run `test_snapshots.py` and `test_render_handler.py` without a database, with a fake provider, a fake
      `PdfRenderer` and a fake uploads call.
    - The same snapshot body with keys in another order → the same `data_hash`. Changing one label (`'Completed'` →
      `'Complete'`) → a different `data_hash`. A body of 6 MB → `SNAPSHOT_TOO_LARGE`.
    - Handler with the fake renderer raising `RenderTimeoutError` and `job.attempts = 1` → raises; with
      `job.attempts = 3` → returns, status `failed`, `error_code = 'RENDER_UNAVAILABLE'`, 1 `report.render_failed`.
    - Handler with a template whose output breaks the HTML policy → returns after 1 try, `failed`,
      `RENDER_CONTRACT_VIOLATION`, and the fake renderer was never called.
    - Handler on a render job already `succeeded` → returns its `file_id`; the fake renderer and the fake store were
      not called.
    - Fake store returning a `sha256` that differs from the PDF's → raises; the status is not `succeeded`.
    - In `test_gotenberg.py` with `httpx.MockTransport` capturing the multipart body:
      `render_html('<p>x</p>', page=PageOptions(210, 297, True, 12, 10, 12, 10))` → fields `landscape=true`,
      `paperWidth=210mm`, `paperHeight=297mm`, `marginTop=12mm`, `preferCssPageSize=false`. With `page=None` → none
      of those fields, only `files`.
  - **integration**:
    - These run `test_render_jobs_db.py` and `test_render_pdf.py` with pytest, testcontainers-python Postgres, the
      TESTING-01 tenants `kaefer-demo` and `tenant-b`, the object-store backend from
      `apps/api/tests/platform/capabilities/conftest.py`, and Gotenberg through its `gotenberg_url` fixture. The
      `project-summary` template is loaded with the REPORTS-01 loader. Add these files to the CI compose step that
      already runs `test_render_store_and_download_report`.
    - As a `kaefer-demo` user with `report.create` and `project.view`, `POST /api/v1/reports/renders
      {templateKey:'project-summary', variant:'internal', recordType:'project', recordId:<KF-01>}` → 202,
      `status: 'queued'`. There is 1 `report_render_jobs` row (`queued`), 1 `report_data_snapshots` row and 1 `jobs`
      row with `job_type = 'report_engine.render'`.
    - Drain the queue with `aip.platform.jobs.app.run_worker(queues=['pdf'], wait=False)` → `GET` gives `status:
      'succeeded'`, a 64-hex `pdfSha256` equal to the sha256 of the bytes from `open_stored_file(fileId)`, and those
      bytes start with `%PDF`. pypdf text of page 1 contains `KF-01`. `domain_events` has 1
      `report.render_succeeded`.
    - Orientation: install a landscape copy of the package as version 2 and render it → pypdf page 1 mediabox is
      842 × 595 pt (±1). The portrait v1 → 595 × 842.
    - The same POST twice with `Idempotency-Key: abc` → the same `id`, 1 render job, 1 snapshot, 1 `jobs` row.
    - Two POSTs without a key and no project change → 2 render jobs, 1 snapshot (same `dataHash`). Rename the
      project, POST again → a second snapshot with a different `dataHash`.
    - Pinning: request with v1 published, publish v2 (with a visible `v2` marker) before draining → the PDF text has
      the v1 marker and `templateVersion: 1`. `POST .../rerender` → a new job with `templateVersion: 1` and the same
      `htmlSha256` as the first.
    - As `aip_app` in `with_tenant`: `UPDATE report_data_snapshots SET data = '{}'` → `permission denied`; `DELETE
      FROM report_data_snapshots` → `permission denied`.
    - Make the `emit` test hook throw inside the request → 500, and 0 `report_data_snapshots`, 0
      `report_render_jobs` and 0 `jobs` rows for that request.
    - Point the renderer at a closed port and drain → the job is tried 3 times, ends `failed` with `errorCode:
      'RENDER_UNAVAILABLE'`, with 1 `report.render_failed` event and no stored file.
    - `templateKey: 'nope'` → 404 `TEMPLATE_NOT_FOUND`. `recordType: 'widget'` with a `widget` template → 422
      `UNKNOWN_RECORD_TYPE`. An `inspection` template with `recordType: 'project'` → 422
      `TEMPLATE_RECORD_TYPE_MISMATCH`.
    - A user with `report.create` but no `project.view` on KF-01 → 403, nothing written. A user with neither → 403.
    - A `tenant-b` user: `GET /api/v1/reports/renders/{kaefer job id}` → 404 `RENDER_JOB_NOT_FOUND`; `POST` with the
      kaefer project id → 404 `RECORD_NOT_FOUND`.
    - Sandbox (`test_gotenberg.py`, the compose Gotenberg with the step 8 flags, calling the adapter directly so the
      REPORTS-01 policy is bypassed): `<p id="x">JS OFF</p><script>document.getElementById('x').textContent='JS
      ON'</script>` → the PDF text contains `JS OFF` and not `JS ON`. `<iframe src="file:///etc/passwd">` → the text
      does not contain `root:`. `<iframe src="http://127.0.0.1:3000/health">` → the text does not contain `status`.
  - **e2e**:
    - No Playwright journey: this task adds no page, and the render path needs the compose Gotenberg and a `pdf`
      worker, which the integration tests above drive end to end on real Postgres and Gotenberg. REPORTS-04 adds the
      browser journey (register, authorised download, cross-tenant 404, axe).
