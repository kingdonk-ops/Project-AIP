# TESTING-04 — Generated permission-matrix and IDOR tests

<!-- hand-edited: depends-on synced from BOARD.md -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ACCESS-01, STACK-03 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/testing/README.md`](../../docs/blueprint/modules/testing/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Generate allow/deny tests from the permissions catalogue and OpenAPI route list.

- **depends on**:
  - TESTING-01
- **files**:
  - backend/tests/access/test_permission_matrix.py
  - backend/tests/access/test_idor.py
  - backend/tests/access/matrix_gen.py
- **steps**:
  - 1. Load the permissions catalogue and role-to-permission seed.
  - 2. Parametrise (role, permission, project in or out of scope, asset subtree in or out of scope).
  - 3. Expect allow only if the grant is present and the scope matches; every other combination must be denied.
  - 4. Read /openapi.json and select routes with an {id} path parameter.
  - 5. For each route, call with tenant B's token and tenant A's id, expecting 404 or 403 and never 200.
  - 6. Write results to a JUnit XML artefact for evidence.
- **acceptance**:
  - Adding a permission to the catalogue automatically adds test cases.
  - Any ID-addressed route that returns 200 cross-tenant fails the build.
  - Deny-by-default is proven: a role with no grants gets 403 on all routes.
- **tests**:
  - **e2e**:
    - Playwright: a client reviewer opens a direct URL to an inspection outside their project and sees the not-found page.
  - **integration**:
    - Role 'Inspector' with inspection:create in project P1: allowed in P1, denied in P2.
    - Asset-subtree-scoped grant on node /plant1/unitA: allowed on /plant1/unitA/pipe5, denied on /plant1/unitB/pipe9.
    - GET /inspections/{tenantA_id} with a B token returns 404.
  - **unit**:
    - matrix_gen yields 4 cases for 1 role x 1 permission x 2 scopes x 2 states, with exactly 1 allow.
