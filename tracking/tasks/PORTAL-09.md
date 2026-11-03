# PORTAL-09 — Portal fixes: register denied state, no-store on every portal response, filter and axe tests

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`portal`](../../docs/blueprint/modules/portal/README.md) |
| Phase | R1 |
| Size | XS |
| Depends on | PORTAL-02, PORTAL-07 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/portal/README.md`](../../docs/blueprint/modules/portal/README.md)
3. [`docs/reviews/13-merged-pr-review-2026-11-03.md`](../../docs/reviews/13-merged-pr-review-2026-11-03.md) (B4, L11, L12)
4. ADRs: 0026, 0036

## Spec

Meet the PORTAL-02 and PORTAL-07 acceptance criteria the review found unmet (tag: harden).

- **files**:
  - apps/web/src/features/portal/PortalUsersRegister.tsx
  - apps/web/src/features/portal/__tests__/portal-users.test.tsx
  - apps/api/aip/modules/portal/routes.py, apps/api/aip/modules/portal/dependencies.py (or the portal error handler)
  - apps/api/aip/modules/portal/tests/test_admin_filters_db.py
  - e2e/web/portal-users.spec.ts
- **steps**:
  - 1. The external users register shows the shared denied state (the one the invite page uses) on a 403, and the
    generic error only for other failures.
  - 2. Every response on the portal host carries `Cache-Control: no-store`, error responses included (404
    `NOT_FOUND`, `RouteHiddenError`, 422, 500). Set it in one place (middleware or the portal error handler), not per
    route.
  - 3. Add the missing tests below.
- **acceptance**:
  - bob, without portal admin rights, opening the register sees the denied state (PORTAL-07 acceptance).
  - No portal-host response lacks `no-store`.
- **tests**:
  - **unit**:
    - register with a mocked 403 → denied state; with a 500 → generic error
    - register has no serious or critical axe violation
  - **integration**:
    - portal 404 (unknown id, hidden route) and 422 responses carry `Cache-Control: no-store`
    - `projectId` combined with `status=invited` narrows further
  - **e2e**:
    - bob on the external users register → denied state (desktop, mobile, iPad; axe)
