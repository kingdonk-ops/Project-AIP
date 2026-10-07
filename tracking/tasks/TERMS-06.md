# TERMS-06 — Glossary and alias mapping for search and import

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | PLAN-R1, TERMS-01 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Provide glossary tooltips and alias mapping so market terms resolve to neutral fields.

- **depends on**:
  - TERMS-01
- **files**:
  - backend/app/modules/terms/aliases.py
  - backend/app/modules/terms/glossary.py
  - backend/tests/terms/test_aliases.py
- **steps**:
  - 1. Implement a CRUD service for glossary_entry (term, abbreviation, definition).
  - 2. Seed CUI, ITP, MDR, WPS and hold/witness/review.
  - 3. Implement alias CRUD, mapping alias to a neutral term or field.
  - 4. Implement expand_query(q, tenant), returning the original plus alias targets.
  - 5. Implement map_headers(columns, tenant) for spreadsheet import, returning matched fields and unmatched columns.
  - 6. Make matching case-insensitive and trimmed.
- **acceptance**:
  - Searching 'punch' also matches 'defect'.
  - An import header 'Deficiency' maps to the neutral defect field.
  - Unmatched columns are reported, not dropped silently.
- **tests**:
  - **e2e**:
    - User searches 'punch' and sees defect records.
  - **integration**:
    - Tenant A's alias is not applied for tenant B.
    - Import preview with the headers 'Punch item','Due' returns 2 mapped and 0 unmapped.
  - **unit**:
    - expand_query('punch') with alias punch to defect returns ['punch','defect'].
    - map_headers([' DEFICIENCY ']) maps to defect_title.
