# PROJECTS-06 — Projects register on RegisterTable, sort direction and CSV export

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`projects`](../../docs/blueprint/modules/projects/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DESIGN-03, PROJECTS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`DESIGN-03.md`](DESIGN-03.md) (the register standard) and [`PROJECTS-02.md`](PROJECTS-02.md)

## Spec

Split out of DESIGN-03 step 8 (2026-10-13): switching the projects register was not a one-line change.

- **steps**:
  - 1. `GET /api/v1/projects` accepts a sort direction (e.g. `sort=-code`) for code, name and updated_at, keeping
    cursor paging stable in both directions.
  - 2. `GET /api/v1/projects/export.csv`: the same filters and the caller's permissions (`project.view`), written
    with `aip.platform.http.csv.to_csv` (the shared golden vectors), streamed, with a row cap.
  - 3. `features/projects` renders `RegisterTable` (`@aip/ui`): the route's `validateSearch` uses
    `decodeRegisterQuery` with the projects spec (keep the `status`, `q`, `cursor`, `limit` param names so existing
    URLs still open), Status as a quick filter, Region hidden by default, Enter opens the project, `exportHref`
    points at step 2. Update the PROJECTS-02 Vitest and Playwright tests.
- **tests**:
  - **integration**: `sort=-code` returns codes descending across pages; the export as a user who sees 7 active
    projects has 1 header row plus 7 data rows; 120 seeded projects with limit 50 give 3 pages (20 on the last).
  - **e2e**: DESIGN-03's journeys on `/projects`: Status=Active, sort by Code descending, hide Region, copy the URL
    into a new page (same state, first row the highest active code); keyboard Tab, ArrowDown, Enter opens the row.

## As built (2026-10-18)

- API: `sort` takes `code|name|updated_at`, `-` first for descending; the cursor carries the direction and is
  refused under another one. Plain `updated_at` is now oldest first (PROJECTS-01 sorted it newest first).
  `GET /api/v1/projects/export.csv` (`projects_export`, `project.view`) takes the list's filters and sort, counts
  first and answers 422 `EXPORT_TOO_LARGE` above 10,000 rows, then streams `csv_header` + keyset batches of
  `csv_row` (new in `aip.platform.http.csv`, byte-identical to `to_csv`). Headers are the API's field names
  (ADR 0033).
- Web: `features/projects` renders `RegisterTable`. The route's search is the canonical encoded register query
  (`validateProjectsSearch` = decode then encode, plus `created`); old `?status=&q=&cursor=&limit=` URLs still
  open (`limit` now one of 25/50/100). The register's generic labels are mapped to the projects terms, so the
  walking skeleton's "Search code or name" and empty-state texts are unchanged.
- `@aip/ui`: `RegisterTable` gained an `empty` slot (the first-run "Create project" call to action) and shows a
  failed request's `requestId` (`register.reference`).
- Enter on a row navigates to `/projects/<id>`, which PROJECTS-07 builds; until then that path is not found.
- e2e: Region is hidden by default, so the copied-URL journey hides Site instead. The register journeys run in the
  stub lane with the list API answered by `page.route`; the server's sort, paging and export are covered by the
  Postgres integration tests (`test_projects_db.py`). The cross-tenant check stays in the walking skeleton.
