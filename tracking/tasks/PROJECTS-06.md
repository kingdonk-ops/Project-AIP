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
