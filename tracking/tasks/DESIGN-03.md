# DESIGN-03 — Register table standard (filters, server pagination, CSV)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`design`](../../docs/blueprint/modules/design/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/design/README.md`](../../docs/blueprint/modules/design/README.md) (the "Register table standard" and "Saved views" bullets)
3. ADRs: 0004 (`packages/ui`, `packages/api-client`)

## Spec

Ship one reusable `RegisterTable` that every P1 register uses: a dense table with sticky header, filter bar and quick filters, URL-addressable state, server-side cursor pagination and sorting, a column chooser, multi-select bulk actions, and permission-respecting CSV export. Saved views are out of scope.

- **files**:
  - packages/ui/src/register/RegisterTable.tsx
  - packages/ui/src/register/FilterBar.tsx
  - packages/ui/src/register/ColumnChooser.tsx
  - packages/ui/src/register/url-state.ts
  - packages/ui/src/register/csv.ts
  - packages/ui/src/register/types.ts
  - packages/ui/src/register/*.test.tsx
  - packages/ui/src/index.ts
- **steps**:
  - 1. In types.ts, define the contract. `RegisterColumn<T> {id, headerKey, cell(row), sortable?, defaultVisible?, mono?}`. `RegisterFilter {id, kind:'select'|'multi'|'text'|'date-range', options?}`. `RegisterQuery {filters, sort:{id, dir}, cursor?, limit}`. Pages have the shape `{items: T[], nextCursor: string|null}`, which matches PROJECTS-01's list endpoint. The component never fetches by itself: it takes `useQuery(query)` (a generated api-client hook adapter) so it stays transport-agnostic.
  - 2. Build RegisterTable on TanStack Table (headless). It has a sticky header, compact row height from `--row-h`, inline StatusChip cells, and keyboard row navigation (arrow keys, Enter opens). Selection uses checkboxes with "select page", and a bulk-action bar appears when one or more rows are selected (actions are passed in, each with an optional `permission` that hides it). Pagination is cursor-based with Previous/Next: a stack of prior cursors kept client-side, page size 25/50/100, and no total count required.
  - 3. Build FilterBar for declared filters plus a free-text `q`, and a quick-filter row for status, assignee, asset and date when the caller declares them. Add "Clear all". Debounce text input by 300ms.
  - 4. In url-state.ts, write an encoder and decoder between `RegisterQuery` and URL search params, using Next's router in the app adapter but a pure function in the package. Unknown params are ignored and invalid values are dropped, not thrown. A copied URL reopens the same filters, sort and visible columns.
  - 5. Build ColumnChooser to toggle visible columns and restore defaults. Store the preference per register id in localStorage for now, behind a `ColumnPrefsStore` interface so a server-backed store can replace it later.
  - 6. In csv.ts, write a pure function `toCsv(columns, rows)` with no DOM use, so the API can stream it too. It produces RFC 4180 quoting and a UTF-8 BOM, and defends against formula injection: cells starting with `=`, `+`, `-`, `@`, tab or CR are prefixed with `'`. The "Export CSV" button calls the caller's `exportHref(query)`, a server endpoint that applies the same filters and the user's permissions, so the client never builds a CSV from more data than it was shown. The button is hidden when no `exportHref` is given.
  - 7. Add empty and loading states (skeleton rows) and an error state with retry, plus the `aria-sort`, `aria-rowcount` (when known) and `aria-selected` attributes. Every header and button label arrives through props or `t()` keys; the component contains no literal text.
  - 8. Write a short usage example in the component's JSDoc. Have PROJECTS-02 switch to RegisterTable if it has already merged (a one-line change in `features/projects`; leave a stub follow-up if that is not trivial).
- **acceptance**:
  - The projects register (or a fixture register) supports filter, sort, next/previous pages, column toggle, multi-select and CSV export, all keyboard-operable.
  - Reloading or sharing the URL restores filters, sort and visible columns.
  - The CSV export always goes through a server endpoint. `toCsv` neutralises formula payloads.
  - axe shows no serious or critical violations in any state (empty, loading, error, selected).
- **tests**:
  - **unit**:
    - `toCsv([{id:'name'}], [{name:'=HYPERLINK("x")'}])` contains `"'=HYPERLINK(""x"")"`. A value with a comma and a newline is quoted. The output starts with `﻿`.
    - `decode(encode({filters:{status:['active','draft']}, sort:{id:'code', dir:'desc'}, limit:50}))` round-trips. `decode('?limit=9999&sort=__proto__')` returns limit 50 (default) and no sort.
    - Previous after two Next clicks requests the first page's cursor. Previous on page 1 is disabled.
    - Selecting 2 rows shows the bulk bar with "2 selected". An action with `permission:'project.archive'` is hidden without that permission.
    - vitest-axe on the empty, loading, error and populated states reports 0 violations.
  - **integration**:
    - Render RegisterTable in apps/web against the compose API with 120 seeded projects and limit 50. Expected: 3 pages, and the third shows 20 rows with Next disabled.
    - Call exportHref with `status=active` as a user who sees 7 active projects. Expected: the CSV has 1 header row plus 7 data rows.
  - **e2e** (Playwright):
    - On `/projects`, set Status=Active, sort by Code descending and hide the Region column, then copy the URL into a new page. Expected: the same filter, sort and columns, and the first row is the highest active code.
    - Using only the keyboard, Tab into the table, ArrowDown to the second row and press Enter. Expected: the row's open action fires.
