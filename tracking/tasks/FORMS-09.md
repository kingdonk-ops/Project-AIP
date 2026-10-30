# FORMS-09 — Template list cursor paging and sort, and who changed each revision

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | FORMS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`FORMS-01.md`](FORMS-01.md) (the template API) and [`FORMS-04.md`](FORMS-04.md) (the register and detail pages that call it)
3. [`DESIGN-03.md`](DESIGN-03.md) (register standard: cursor paging, server-side sort) and [`PROJECTS-06.md`](PROJECTS-06.md) (a register on cursor pages)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md), [0036](../../docs/adr/0036-r1-module-decisions.md)

## Spec

Bring the form template list up to the register standard and show who made each revision, found while building FORMS-04 (tag: extend).

FORMS-04 found two gaps in the FORMS-01 API: `GET /api/v1/forms/templates` returns at most 200 templates ordered by code, with no cursor and no sort, so the register cannot page past 200 or sort; and the revision summaries in `GET /templates/{id}` carry no `createdBy` / `publishedBy`, so the history cannot say who published a revision.

- **files**:
  - apps/api/aip/modules/forms/routes.py
  - apps/api/aip/modules/forms/schemas.py
  - apps/api/aip/modules/forms/repository.py
  - apps/api/aip/modules/forms/service.py
  - apps/api/aip/modules/forms/tests/test_forms_db.py
  - packages/api-client (regenerated)
  - apps/web/src/features/forms/search.ts
  - apps/web/src/features/forms/TemplatesRegister.tsx
  - apps/web/src/features/forms/RevisionHistory.tsx
- **steps**:
  - 1. `GET /templates` gains `cursor` and `sort` (`code`, `-code`, `name`, `-name`, `updated_at`, `-updated_at`) and returns `{items, nextCursor}` like `GET /projects`; `limit` defaults to 50.
  - 2. `RevisionSummary` gains `createdBy` and `publishedBy` (user ids) and their display names through the identity published interface.
  - 3. Regenerate the client; the FORMS-04 register uses cursor pages and sortable code, name and updated columns; the history shows "Published by".
- **acceptance**:
  - The register pages forward and back through 60 templates at 25 a page and sorts both ways on code, name and updated.
  - The history names the user who published each revision.
- **tests**:
  - **unit**:
    - `toListParams` maps `sort=-name` and a cursor to the API parameters.
  - **integration**:
    - 3 templates, `limit=2` → 2 items and a `nextCursor`; the next page → 1 item and `nextCursor: null`; `sort=-code` reverses the order; another tenant's templates never appear.
  - **e2e**:
    - Extend `e2e/web/form-templates.spec.ts`: the history row of v1 shows the admin's name as publisher.
