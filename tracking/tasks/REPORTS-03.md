# REPORTS-03 — Inspection report on approval: internal and client variants, landscape

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | IDENTITY-09, INSPECTIONS-02, REPORTS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`REPORTS-01.md`](REPORTS-01.md) (template package and render contract) and [`REPORTS-02.md`](REPORTS-02.md) (providers, snapshots, `ReportsApi.request_render`, the render job)
3. [`INSPECTIONS-01.md`](INSPECTIONS-01.md) (`InspectionsApi.get_inspection`, `inspection.state_changed` v1) and [`INSPECTIONS-02.md`](INSPECTIONS-02.md) (`InspectionsApi.get_current_responses`)
4. [`FORMS-01.md`](FORMS-01.md) (the form template contract: sections, fields, `labelKey`, field types) and [`APPROVALS-05.md`](APPROVALS-05.md) (the inspection preset: `completed` is the approved, terminal state in both variants)
5. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md) ("Auto-generate on approval", "Internal, client and certificate variants", landscape for coating/DFT reports)
6. ADRs: [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox subscribers), [0014](../../docs/adr/0014-ofl-fonts-allowed.md) (embedded fonts), [0025](../../docs/adr/0025-time-and-timezones.md) (show times in the project's zone), [0030](../../docs/adr/0030-outbox-dispatch-semantics.md) (subscribers share one transaction and may run twice), [0036](../../docs/adr/0036-r1-module-decisions.md)
7. Code: `apps/api/aip/platform/events/subscribers.py` (`@subscriber`, `DomainEvent`, manifest `[[subscribes]]`)

## Spec

When an inspection reaches its approved state, render its report automatically in an internal and a client variant, both landscape A4 for coating and DFT readings, from a snapshot of the inspection, its asset, project, pinned form revision and current answers taken in the same transaction as the approval event (tag: extend).

Prerequisite outside this module: the sign-off block needs the approver's display name, and no published interface
gives one today (`aip.modules.identity.api` has no user lookup). This task calls
`aip.modules.identity.api.get_display_names(conn, user_ids) -> dict[UUID, str]`. If that has not merged when this task
IDENTITY-09 (a dependency of this row) adds it. Out of scope: publishing,
distribution and numbering (REPORTS-06), the golden CUI report (REPORTS-05), per-field client visibility in form
templates (no R1 row), hold-point sign-offs (INSPECTIONS-03 data; a later report version adds them).

- **files**:
  - apps/api/aip/modules/report_engine/manifest.toml
  - apps/api/aip/modules/report_engine/events.py
  - apps/api/aip/modules/report_engine/auto_render.py
  - apps/api/aip/modules/report_engine/providers/__init__.py
  - apps/api/aip/modules/report_engine/providers/inspection.py
  - apps/api/aip/modules/report_engine/template_package.py
  - apps/api/aip/modules/report_engine/repository.py
  - apps/api/aip/modules/report_engine/tests/test_inspection_provider.py
  - apps/api/aip/modules/report_engine/tests/test_inspection_templates.py
  - apps/api/aip/modules/report_engine/tests/test_auto_render_db.py
  - apps/api/aip/modules/report_engine/tests/fixtures/inspection-coating.json
  - packages/contracts/report-templates/report-template.schema.json
  - config/report-templates/inspection/internal/v1/template.json
  - config/report-templates/inspection/internal/v1/body.html.j2
  - config/report-templates/inspection/internal/v1/style.css
  - config/report-templates/inspection/internal/v1/sample-data.json
  - config/report-templates/inspection/internal/v1/assets/logo.png
  - config/report-templates/inspection/client/v1/template.json
  - config/report-templates/inspection/client/v1/body.html.j2
  - config/report-templates/inspection/client/v1/style.css
  - config/report-templates/inspection/client/v1/sample-data.json
  - config/report-templates/inspection/client/v1/assets/logo.png
  - config/terms/en-AU/report_engine.json
- **steps**:
  - 1. **Auto-render in the template contract.** Add an optional `autoRender` object to
    `report-template.schema.json`: `{"onStates": ["completed"]}` (1–10 state codes matching `^[a-z][a-z_]{1,40}$`,
    `additionalProperties: false`). `template_package.py` accepts it only when `recordType` has an auto-render
    trigger (R1: `inspection`), else `SCHEMA_INVALID` at path `autoRender`. Turning auto-render off is a new template
    version without `autoRender`, or retiring the template: the rule is data, versioned like the rest of the
    template. No new table, so no migration.
  - 2. **Inspection data provider** (`providers/inspection.py`), registered for record type `inspection` with view
    permission `inspection.view`. `provide(conn, inspection_id, *, context)`:
    - (a) `aip.modules.inspections.api.InspectionsApi.get_inspection(conn, inspection_id)`; `None` → `RecordNotFound`.
      `record_version` = the inspection's `sync_version`.
    - (b) `aip.modules.assets.api.AssetsApi.get_asset(conn, inspection.asset_id)` (tag number, name, internal tag,
      and the ancestor names for the location line) and `aip.modules.projects.api.ProjectsApi.get_project(conn,
      inspection.project_id)` (code, name, `timezone`, which becomes the snapshot `timeZone`).
    - (c) `aip.modules.forms.api.FormsApi.get_revision(conn, inspection.template_revision_id)` (the pinned revision,
      also when superseded) and `InspectionsApi.get_current_responses(conn, inspection_id)`.
    - (d) Shape `record` as `{inspection: {id, kind, state, createdAt}, asset: {tagNumber, name, internalTag,
      location: [names root first]}, project: {code, name, timezone}, form: {code, revisionNo, schemaHash, sections:
      [{key, label, fields: [...]}]}, summary: {answered, failed, missingRequired}, approval: {approvedAt,
      approvedBy}}`. Each field: `{key, type, label, unit, required, failed, answer, respondedBy, respondedAt}`.
      - Only fields that are visible in the current evaluation (`evaluation.visible`) are included, in schema order.
      - `label` is the form's own text, or, when the field has a `labelKey`, the text resolved with
        `aip.modules.terms.api.bulk_resolve`, so form labels are frozen in the snapshot as display text.
      - `answer` by type: `measurement` → `{valueSi: to_si(value, unit), unit}` (via `aip.modules.terms.api.to_si`;
        the template shows it with `fmt_measure`); `dropdown` and `multi_select` → the option labels;
        `boolean` → `true`/`false` (the template shows term labels); `photo` and `signature` → file references
        (below); `date` → the ISO date; others → the value.
      - `respondedBy` is resolved to a display name with `get_display_names` (see the prerequisite). `respondedAt`
        stays UTC.
    - (e) Photos and signatures: each referenced stored file goes into `ReportSource.files` with role
      `photo:<fieldKey>` or `signature:<fieldKey>`. Only `image/jpeg`, `image/png` and `image/webp` files of at most
      3 MB each are embedded, and at most 40 per report in schema order. Anything else stays in the record as
      `{fileId, omitted: 'too_large' | 'too_many' | 'not_an_image'}`, which the template shows with
      `report.inspection.photo_omitted.<reason>`.
    - (f) `context` (from the trigger) gives `approval.approvedAt` (the event's `occurred_at`) and
      `approval.approvedBy` (the event's `actor_id`, as a display name). A manual render has an empty `approval`.
  - 3. **Templates** in `config/report-templates/inspection/`, key `inspection`, record type `inspection`, both
    `orientation: landscape`, `paper: A4`, `marginsMm` 10/10/12/10, `autoRender: {"onStates": ["completed"]}`:
    - `internal/v1`: header (logo, `t('report.inspection.title')`, project code and name, asset Tag Number, internal
      tag and location), summary band (answered, failed and missing counts; failed count highlighted), one table per
      section with columns label, answer, unit, result (`t('report.inspection.result.pass')` / `.fail`), responder
      and time (`fmt_datetime` in the project zone), a photo grid (`asset('file-<id>.<ext>')`, 4 per row, with
      captions), the sign-off block (approved by, approved at, with the zone abbreviation) and a footer with the
      form code and revision, template version, `dataHash` (first 12 characters) and page numbers.
    - `client/v1`: the same layout without the responder column, the internal tag, the form schema hash and any
      inspection or user ids. The client sees Tag Number, answers, results, photos, and the approval date and
      approver name.
    - Every visible word is a term key in `termKeys`, with en-AU defaults in `config/terms/en-AU/report_engine.json`
      (`report.inspection.*`). Long tables repeat their header row on each page (`thead { display:
      table-header-group }`) and rows do not split (`tr { break-inside: avoid }`).
    - `sample-data.json` in each package is the `inspection-coating` fixture shape, so the REPORTS-01 preview works.
  - 4. **Subscriber** (`events.py` and `auto_render.py`): `@subscriber("inspection.state_changed", 1)`, with
    `[[subscribes]] name = "inspection.state_changed"`, `version = 1` in the manifest.
    `on_inspection_state_changed(conn, event)`:
    - (a) `repository.list_auto_render_templates(conn, record_type="inspection", state=event.payload["to"])`: the
      latest published version per `(key, variant)` whose `definition.autoRender.onStates` contains the state.
      None → return.
    - (b) For each, inside a savepoint (`conn.begin_nested()`), call `RenderService.request_render(conn,
      template_key=key, record_type="inspection", record_id=inspectionId, variant=variant,
      requested_by=event.actor_id, idempotency_key=f"auto:{event.id}:{key}:{variant}", trigger_event_id=event.id)`,
      passing `context={approvedAt: event.occurred_at, approvedBy: event.actor_id}` to the provider.
    - (c) A report request error (`TEMPLATE_NOT_FOUND`, `RECORD_NOT_FOUND`, `SNAPSHOT_TOO_LARGE`, ...) rolls back
      only that savepoint and is logged with the event id, template key, variant and error code, never the record
      data. The subscriber does not raise, so the other subscribers of the same event (they share one transaction,
      ADR 0030) still commit. Any other exception is raised, so the dispatcher retries the event.
    - (d) Idempotent on `event.id`: a repeat delivery finds the render jobs by idempotency key and creates nothing.
    - No policy check: this is a system action triggered by an approval that the transition service has already
      authorised. Manual renders through `POST /api/v1/reports/renders` keep REPORTS-02's `report.create` plus
      `inspection.view` check.
  - 5. **Loader and compose.** The two packages install with the REPORTS-01 loader. The `report-templates-load`
    one-shot already loads all of `config/report-templates`, so the dev tenants get them on the next `compose up`.
- **acceptance**:
  - Approving an inspection (`supervisor_review` → `completed` in `inspection.standard`, or `client_review` →
    `completed` in `inspection.client-review`) queues exactly one internal and one client render, each with its own
    snapshot taken in the approval event's dispatch transaction, and both reach `succeeded` on the `pdf` worker.
  - Both PDFs are landscape A4. The client PDF contains no responder names, internal tags or ids.
  - Redelivering the event creates nothing new. A report failure never rolls back another subscriber's work for the
    same event.
  - Hidden fields (`visibleIf` false) are not in the report, and failed answers are marked as failed.
- **tests**:
  - **unit**:
    - These run `test_inspection_provider.py` and `test_inspection_templates.py` with no database (fake published
      interfaces).
    - The provider on the `inspection-coating` fixture (FORMS-01's `coating-itr-min` form: `surface_prepared =
      true`, `dft_avg = {value: 0.2, unit: 'mm'}` failed, 2 photos, `remarks` hidden by `visibleIf`) → 5 fields
      (no `remarks`), `summary.failed = 1`, `dft_avg.answer.valueSi = 0.0002`, `dft_avg.failed = true`, and 2
      `files` with role `photo:photos`.
    - A field with `labelKey: 'coating.dft_average'` → its `label` is the resolved en-AU text, not the key.
    - 41 photo files → 40 in `files` and 1 `{omitted: 'too_many'}`. A 4 MB JPEG → `too_large`. A PDF in a photo
      field → `not_an_image`.
    - `InspectionsApi.get_inspection` returning `None` → `RecordNotFound`.
    - Render `internal/v1` with its sample data (REPORTS-01 `render_html`) → contains `@page { size: A4 landscape;`,
      the Tag Number `P-1001`, the responder name `Ivy Inspector` and the failed label `Fail`. Render `client/v1` → it
      contains `P-1001` and `Fail`, and does not contain `Ivy Inspector`, the internal tag or any 36-character uuid.
    - Both packages pass `load_package` (HTML and CSS policy, schema) and every term key they use exists in
      `config/terms/en-AU/report_engine.json` → 0 missing.
    - A package with `autoRender` and `recordType: 'project'` → `SCHEMA_INVALID` at path `autoRender`.
    - Subscriber with a fake `RenderService`: `to = 'in_progress'` → 0 calls. `to = 'completed'` → 2 calls with
      idempotency keys `auto:<eventId>:inspection:internal` and `auto:<eventId>:inspection:client`. The fake raising
      `RECORD_NOT_FOUND` on the first call → the second call still happens, and the subscriber does not raise.
  - **integration**:
    - These run `test_auto_render_db.py` with pytest, testcontainers-python Postgres, the TESTING-01 tenants
      `kaefer-demo` and `tenant-b`, and Gotenberg through the `gotenberg_url` fixture (in the CI compose step with
      REPORTS-02's tests). Set-up: install the `inspection.standard` preset (APPROVALS-05), load both report packages
      with the loader, create an asset `P-1001` with `AssetsApi.create_asset`, publish the `coating-itr-min` form,
      create an inspection with `InspectionsApi.create_inspection`, answer it (`dft_avg` 0.2 mm, 2 photos stored with
      `store_generated_file`), and take it to `supervisor_review`.
    - `approve` as the supervisor (an aal 2 session), then dispatch the outbox once → 2 `report_render_jobs` rows
      (`variant` internal and client), both `queued` with `trigger_event_id` = the `inspection.state_changed` event id
      and `requested_by` = the supervisor, plus 2 `report_data_snapshots` rows.
    - Dispatch the same event again → still 2 render jobs and 2 snapshots.
    - Drain the `pdf` queue → both `succeeded` with 64-hex `pdfSha256`. pypdf: every page of both PDFs is landscape
      (mediabox width 842 > height 595). The internal PDF's text contains `P-1001`, the en-AU failed label and the
      inspector's display name, and page 1 has at least 2 images. The client PDF's text contains `P-1001` and not the
      inspector's display name.
    - A transition to `in_progress` on another inspection → 0 render jobs for it.
    - Publish `inspection/client` v2 without `autoRender`, then approve a second inspection → 1 render job
      (internal only).
    - Isolation: register a test subscriber on `inspection.state_changed` that inserts a marker row, make the
      inspection provider raise `RecordNotFound`, approve → the marker row is committed, 0 render jobs exist for that
      inspection, and the log line has the event id and `RECORD_NOT_FOUND`.
    - Approving an inspection in `tenant-b` (which has no inspection report templates loaded) → 0 render jobs in
      `tenant-b`. A `tenant-b` user calling `GET /api/v1/reports/renders/{kaefer render id}` → 404
      `RENDER_JOB_NOT_FOUND`.
    - `POST /api/v1/reports/renders {templateKey:'inspection', variant:'client', recordType:'inspection', recordId}`
      by a user with `report.create` but without `inspection.view` → 403, nothing written. With both → 202, and the
      new job has an empty `approval` in its snapshot.
  - **e2e**:
    - No Playwright journey: approval needs a supervisor session at assurance level 2 and a running `pdf` worker, and
      the integration test above drives the whole chain on real Postgres and Gotenberg. REPORTS-04 adds the browser
      journey that finds and downloads these reports, and REPORTS-05 pins the golden PDF on CUI data.
