# PROJECTS-05 — System sites are hidden and protected

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`projects`](../../docs/blueprint/modules/projects/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | PROJECTS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `apps/api/aip/modules/projects/service.py` (`SiteService`)

## Spec

Owner decision (2026-10-13, from the PROJECTS-01 security review): a system site (`sites.is_system`,
the hidden per-project root of the asset hierarchy that the platform creates) must never be shown,
renamed or deleted through the API. Nothing creates system sites yet; the rule is in place before
anything does.

- **files**:
  - apps/api/aip/modules/projects/service.py
  - apps/api/aip/modules/projects/tests/test_projects_db.py
- **steps**:
  - 1. `GET /sites` leaves out system sites; `GET /sites/{id}` returns 404 for one.
  - 2. `PATCH /sites/{id}` and `DELETE /sites/{id}` on a system site return 409 `SITE_IS_SYSTEM` and change nothing.
- **acceptance**:
  - A seeded system site is absent from the list and search, 404 on get, 409 `SITE_IS_SYSTEM` on edit and delete, and unchanged in the database.
- **tests**:
  - **unit**:
    - none
  - **integration**:
    - `test_system_sites_are_hidden_and_cannot_be_changed` in `projects/tests/test_projects_db.py`.
  - **e2e**:
    - none
