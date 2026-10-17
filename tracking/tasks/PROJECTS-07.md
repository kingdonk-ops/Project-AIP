# PROJECTS-07 — Project detail page and sites register

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`projects`](../../docs/blueprint/modules/projects/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | DESIGN-04, PROJECTS-06 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/projects/README.md`](../../docs/blueprint/modules/projects/README.md)
3. ADRs: 0018
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M13**. `GET/PATCH /projects/{id}` and site CRUD exist (`projects/routes.py:77-164`), but the
web uses only list, create and sites-list. There is no `/projects/$projectId` route. AUDIT-04 step 5 mounts its
History tab on a project detail page, so AUDIT-04 depends on this task.

## Spec

Users can open, edit and archive a project and manage its sites in the web app.

- **files**:
  - apps/web/src/routes/_app/projects/$projectId*
  - apps/web/src/ (sites register, forms)
  - e2e/web/
- **steps**:
  - 1. Add `/projects/$projectId` using RecordDetail (DESIGN-04) with edit and lifecycle/archive.
  - 2. Add a sites register (RegisterTable) with create, edit and delete.
  - 3. Leave a tab slot for AUDIT-04's History tab.
- **acceptance**:
  - A user with the permissions can open, edit and archive a project and manage its sites.
  - Without them, the actions are hidden and the server 403 is handled.
  - Terminology keys only.
- **tests**:
  - **unit**:
    - detail page renders loading, error and not-found states
  - **e2e**:
    - open a project from the register, edit its name, add a site, archive it
    - tenant B opening tenant A's project id → 404; axe clean
