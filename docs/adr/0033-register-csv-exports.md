# ADR 0033: Register CSV exports: field-name headers, streamed, capped, sorted like the list

- **Status:** accepted
- **Date:** 2026-10-18
- **Affects:** projects (PROJECTS-06), design (DESIGN-03 `RegisterTable` export), every later register with an export

## Context

DESIGN-03 gave `RegisterTable` an "Export CSV" link to a module endpoint that applies the same filters
and the caller's permissions, written with `aip.platform.http.csv.to_csv` (shared golden vectors).
PROJECTS-06 builds the first such endpoint, `GET /api/v1/projects/export.csv`, and has to decide
what the header row says, how big a file may be, and how list sorting takes a direction.

User-facing text must come from terminology keys, but the server has no locale for a request yet
(the terms module resolves keys for a tenant and a locale, and no route negotiates one), and a file
that changes its headers per tenant terminology is harder to re-import or script against.

## Decision

- **Headers are the API's JSON field names** (`code,name,status,siteId,region,updatedAt`) and values
  are the API's stable codes (`active`, ISO timestamps), exactly as `GET` returns them. An export is a
  data file, like the API, not a page; it is the same in every tenant and locale.
- **Sort direction** is a leading `-` on the `sort` parameter (`sort=-code`), for every sortable
  column, the same form as the register URL. A cursor records the sort it was issued for, direction
  included, and is refused (`INVALID_CURSOR`) under any other. Plain `updated_at` is now oldest first;
  newest first is `-updated_at`.
- **Exports stream and are capped.** The endpoint counts the matching rows first and answers
  `422 EXPORT_TOO_LARGE` (with `limit`) above the cap (10,000 for projects) rather than truncating
  silently; it then streams the header and keyset batches (500 rows, each batch in its own tenant
  transaction under the request's context), using `csv_header` + `csv_row`, whose concatenation is
  byte-identical to `to_csv`.
- Exports take the list's filters and sort but no `limit` or `cursor`, and need the list's
  permission (`project.view` for projects).

## Consequences

- Every later export reuses the same shape; its columns are listed in the module's service next to
  the cap.
- A localised header row (resolved through terms, with the request's locale) can be added later as an
  opt-in parameter without breaking files people already script against.
- Batches read in separate transactions: a row changed mid-export can appear in its new position or
  be missed, as with paging the list. That is accepted for a register export.
