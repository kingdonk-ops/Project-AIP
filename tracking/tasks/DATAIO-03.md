# DATAIO-03 — Import wizard pages: template download, mapping, dry-run report, commit and history

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`data_io`](../../docs/blueprint/modules/data_io/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DATAIO-02, DESIGN-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`DATAIO-01.md`](DATAIO-01.md) and [`DATAIO-02.md`](DATAIO-02.md) (the `/api/v1/imports` API these pages drive)
3. [`docs/blueprint/modules/data_io/routes.md`](../../docs/blueprint/modules/data_io/routes.md) (import wizard, asset tree import preview, import history) and [`ui-layout.md`](../../docs/blueprint/modules/data_io/ui-layout.md); the real routes are the ones below, not `/p/:projectId/...`
4. [`DESIGN-04.md`](DESIGN-04.md) (record detail, dialogs, toasts, empty/loading/error states), [`PROJECTS-06.md`](PROJECTS-06.md) (`RegisterTable` in a feature)
5. ADRs: [0018](../../docs/adr/0018-module-groups-and-navigation.md) (nav groups), [0025](../../docs/adr/0025-time-and-timezones.md) (local time at presentation), [0033](../../docs/adr/0033-register-csv-exports.md), [0036](../../docs/adr/0036-r1-module-decisions.md)

> Scope. Pages only: no migration and no new API except what step 1 notes. The upload uses the existing uploads
> session API directly; the shared upload tray is UPLOADS-06 and is not needed here. Update-by-key (DATAIO-05) adds a
> mode selector later; export pages are not R1.

## Spec

Give users with `import.run` a wizard to pick an importer, download its template, upload a CSV or XLSX through the uploads pipeline, map columns, read the dry-run report (row errors and, for asset trees, the hierarchy preview), commit, and review past imports with batch rollback (tag: extend).

- **files**:
  - apps/web/src/features/data_io/nav.ts
  - apps/web/src/features/data_io/api.ts
  - apps/web/src/features/data_io/upload.ts
  - apps/web/src/features/data_io/search.ts
  - apps/web/src/features/data_io/ImportHistory.tsx
  - apps/web/src/features/data_io/NewImport.tsx
  - apps/web/src/features/data_io/ImportJobPage.tsx
  - apps/web/src/features/data_io/MappingStep.tsx
  - apps/web/src/features/data_io/DryRunReport.tsx
  - apps/web/src/features/data_io/TreePreview.tsx
  - apps/web/src/features/data_io/RollbackDialog.tsx
  - apps/web/src/features/data_io/data_io.css
  - apps/web/src/features/data_io/__tests__/helpers.tsx
  - apps/web/src/features/data_io/__tests__/upload.test.ts
  - apps/web/src/features/data_io/__tests__/mapping.test.tsx
  - apps/web/src/features/data_io/__tests__/dry-run-report.test.tsx
  - apps/web/src/features/data_io/__tests__/import-history.test.tsx
  - apps/web/src/routes/_app/import/index.tsx
  - apps/web/src/routes/_app/import/new.tsx
  - apps/web/src/routes/_app/import/$jobId.tsx
  - apps/web/src/router.ts
  - config/terms/en-AU/data_io.json
  - e2e/web/data-io-import.spec.ts
  - e2e/fixtures/asset-tree-import.csv
- **steps**:
  - 1. Use the generated client (`packages/api-client`) for every call: the `/api/v1/imports` operations from
    DATAIO-01/02 and `uploads_create_session` / `uploads_confirm_session` / `uploads_session_status`. Add no API. If
    the session status does not expose the stored `fileId` once the file is clean, stop and raise it against
    UPLOADS-08 instead of working around it.
  - 2. `nav.ts`: `registerNavItem({id: "import", section: "work-assets", to: "/import", icon: <an existing icon>,
    termKey: "data_io.nav.title", permission: "import.view"})`. Routes (created with `createRoute` under `appRoute`,
    added in `router.ts`): `/import` (history), `/import/new` (start), `/import/$jobId` (one job). Each page checks
    the session's permissions like the projects pages; the API stays the authority.
  - 3. `/import` — `ImportHistory` on `RegisterTable`, its query in the URL (`decodeRegisterQuery` with a data_io
    spec): columns created (local time, ADR 0025), importer (term label), file name, project, requested by, status
    (`StatusChip` with `data_io.status.<status>`), rows, errors, created count; quick filter Status; "New import"
    button (only with `import.run`); Enter or click opens `/import/<id>`; empty state from DESIGN-04 with the same
    call to action.
  - 4. `/import/new` — `NewImport`:
    - Importer select from `GET /imports/importers` (only kinds the caller may run; none → empty state
      `data_io.new.no_importers`), project select, and the importer's options (for `asset_tree`: item type select and
      parent resolution `tag_number`/`path` with the separator).
    - "Download template" link to `GET /imports/importers/{kind}/template.csv` with the options as query parameters.
    - File input accepting `.csv` and `.xlsx`; files over the `GET /imports/limits` size are refused in the browser
      with `data_io.error.FILE_TOO_LARGE` before any upload (the server re-checks).
    - `upload.ts`: create the uploads session, POST the bytes to the presigned URL with its fields, confirm, then
      poll the session status every 2 s (at most 5 minutes) until clean or rejected. Rejected → the scan reason's term
      text. Clean → `POST /imports {kind, projectId, fileId, options}` and navigate to `/import/<id>`. Progress shows
      uploading → scanning → ready with a live region (`aria-live="polite"`).
  - 5. `/import/$jobId` — `ImportJobPage`, a `RecordDetail` (DESIGN-04) titled with the file name, status chip, and a
    `WorkflowBar` of the steps Upload → Map → Dry run → Commit, the current step from the job status:
    - **Map** (`uploaded`, `dry_run_ready`, `failed`): `MappingStep` lists each file header with a select of the
      importer's fields (or "Do not import"), pre-filled from `suggestedMapping` or the saved mapping; required fields
      not yet mapped are listed above the table; "Save and run dry run" PUTs the mapping (sending `syncVersion`) then
      POSTs `dry-run`. 422 `MAPPING_INVALID`/`MAPPING_INCOMPLETE` show inline against the fields named; 409 shows the
      DESIGN-04 conflict state with a reload action.
    - **Dry run** (`validating`): a loading state; the page polls `GET /imports/{id}` every 2 s and stops on a
      terminal or ready status (and when the tab is hidden, resuming on focus).
    - **Report** (`dry_run_ready`, `failed`): `DryRunReport` shows the counts, the error codes with their counts, a
      paged errors table (row, column, problem as term text with params, value shown as plain text), "Download error
      report" linking `errors.csv`, and a `failure_code` banner for file errors (`FILE_TOO_LARGE`, `TOO_MANY_ROWS`,
      `ENCODING_UNSUPPORTED`, ...). For `asset_tree`, `TreePreview` renders `dryRunResult.preview` as an ARIA `tree`
      (expand/collapse with arrow keys; `new` and `existing` markers as text plus colour; a "truncated" note at 500
      nodes) beside counts of roots, attached-to-existing, orphans, duplicates and cycles.
    - **Commit**: enabled only when `errorCount = 0`; a `confirm` dialog states the importer and the number of records
      to create; on 202 the page polls until `committed` (toast `data_io.commit.done` with the created count) or
      `failed` (banner with `failure_code`). With errors the button is disabled and its description says to fix the
      file and upload again ("Upload a corrected file" returns to `/import/new` with the same importer, project and
      options in the search params).
    - **Committed / rolled back**: the batch panel from `GET /imports/{id}/batch` (counts, rollback state, blockers),
      and "Roll back batch" (only with `import.rollback`) opening `RollbackDialog` (reason, 3–500 characters,
      required). 409 `ROLLBACK_BLOCKED` lists each blocker as term text with its tag; success shows the
      `rolled_back` status and a toast.
    - "Cancel import" (`uploaded`, `dry_run_ready`, `failed`) through `confirm`, then back to `/import`.
    - 404 from `GET /imports/{id}` shows the app's not-found state (another tenant's id and a wrong id look the same).
  - 6. Every label is a term key with an en-AU default in `config/terms/en-AU/data_io.json` (nav, page titles,
    steps, buttons, column headers, statuses, every error code the API returns, preview markers, dialog texts).
- **acceptance**:
  - A user can go from template download to a committed import and back to a rolled-back batch without leaving the
    wizard, and every step's state survives a page reload (it comes from the job, not from the browser).
  - Commit is impossible from the UI while the dry run has errors; the error report downloads as CSV.
  - The asset-tree preview is keyboard-operable and shows new and existing nodes without relying on colour.
  - Users without `import.view` do not see the nav item and get the forbidden state on `/import`; users without
    `import.run` see history but no "New import", mapping or commit actions.
  - No serious or critical axe violations on the three pages.
- **tests**:
  - **unit** (Vitest, Testing Library, the API answered by MSW-style handlers in `__tests__/helpers.tsx`):
    - `upload.ts` with session status answers `pending`, `pending`, `clean` → resolves with the `fileId` after 3
      polls; with `rejected` (reason `virus_found`) → rejects with that reason; still `pending` after 5 minutes of
      fake timers → rejects with `data_io.error.SCAN_TIMEOUT`.
    - A 12 MiB file with the limit at 10 MiB → `FILE_TOO_LARGE` shown and no session created.
    - `MappingStep` with headers `["Tag Number","Name","Notes"]`, required fields `tag_number`, `name` and
      suggested mapping `{"Tag Number": "tag_number"}` → `name` listed as missing and "Save and run dry run" disabled;
      choosing `Name → name` enables it; the PUT body is `{mapping: {"Tag Number": "tag_number", "Name": "name",
      "Notes": null}, expectedSyncVersion: 3}`.
    - A 422 `MAPPING_INVALID` with `fields: ["name"]` → the error appears on the `name` row.
    - `DryRunReport` for `errorCount = 2` → Commit disabled with its description; for `errorCount = 0` → enabled,
      and confirming POSTs `commit`.
    - An error with `rawValue = "=2+3"` renders as the literal text `=2+3` (no link, no markup).
    - `TreePreview` with `SITE-1 (existing) → U-100 (new) → V-101 (new)` → `role="tree"`, 3 `treeitem`s, ArrowRight
      on `U-100` expands it, and each item's accessible name includes its marker text.
    - `ImportHistory` without `import.run` → no "New import" button; with it → the button links to `/import/new`.
    - `RollbackDialog` 409 `ROLLBACK_BLOCKED` with `[{code: "edited_since_import", tag: "V-101"}]` → the blocker
      text names `V-101` and the dialog stays open.
  - **integration**:
    - The page logic runs against the real API in e2e; the API behaviour is proven by DATAIO-01/02's Postgres tests.
  - **e2e** (`e2e/web/data-io-import.spec.ts`, Playwright, the compose-stack lane with real sessions like
    `uploads-presign.spec.ts`, skipped where the fixture credentials are absent; `@axe-core/playwright`):
    - Main journey as the `kaefer-demo` importer fixture (with `import.run`, `import.rollback`, `asset.create`,
      `asset.delete`) and an existing root asset `SITE-1` with a run-id suffix: open `/import` → "New import" →
      importer "Asset tree", the e2e project and the fixture item type → download the template (the download's first
      line contains `tag_number,name`) → upload `e2e/fixtures/asset-tree-import.csv` (3 rows under `SITE-1`, one with
      a formula-looking name `=2+3`) → scanning then ready → mapping pre-filled → run dry run → report shows 1 error,
      `formula_injection` on that row, Commit disabled → upload a corrected file → dry run with 0 errors and the tree
      preview showing `SITE-1` (existing) with 3 new descendants → Commit → confirm → status Committed and created
      count 3 → "Roll back batch" with a reason → status Rolled back. The history at `/import` lists the job first
      with status Rolled back.
    - Cross-tenant: a `tenant-b` user opening `/import/<the kaefer job id>` sees the not-found state, and `/import`
      as that user does not list the job.
    - Axe on `/import`, `/import/new` and `/import/<id>` in the report step → no serious or critical violations.
