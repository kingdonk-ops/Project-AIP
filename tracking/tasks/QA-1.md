# QA-1 — Walking-skeleton: "Create project" link is ambiguous on an empty register

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`testing`](../../docs/blueprint/modules/testing/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | TESTING-09 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. `e2e/web/walking-skeleton.spec.ts`

## Spec

Make the walking-skeleton journey deterministic when tenant A's project register is empty.

`ProjectsRegister` renders a "Create project" link in the header and, when the list is empty and
unfiltered, a second one in the empty state. The spec clicked `getByRole("link", { name: "Create project" })`,
which passes only if it clicks before the list query resolves; otherwise Playwright's strict mode fails
(seen on PR #70, `e2e-skeleton`, run 38633234242).

- **files**:
  - e2e/web/walking-skeleton.spec.ts
- **steps**:
  - 1. Click the first (header) "Create project" link.
- **acceptance**:
  - `e2e-skeleton` passes whether or not the register has finished loading when the link is clicked.
- **tests**:
  - **e2e**:
    - empty register, list loaded → header link clicked, create form opens
