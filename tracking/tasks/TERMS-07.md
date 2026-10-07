# TERMS-07 — Hard-coded string linter and coverage report

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TERMS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Fail CI on raw labels such as ITP, NCR or Variation in templates and API names.

- **depends on**:
  - TERMS-01
- **files**:
  - backend/app/modules/terms/lint.py
  - backend/tests/terms/test_lint.py
  - .github/workflows/ci.yml
  - frontend/eslint-rules/no-hardcoded-labels.js
- **steps**:
  - 1. Scan the Jinja email and PDF templates and API response label fields for literal terms from a deny-list built from the dictionary defaults.
  - 2. Add an allow-list file with reasons.
  - 3. Produce a findings JSON with file, line and suggested key.
  - 4. Add an ESLint rule flagging JSX text that matches the deny-list.
  - 5. Run both in CI.
  - 6. Persist the findings for the admin coverage report endpoint.
- **acceptance**:
  - A literal 'NCR' in a template fails CI.
  - An allow-listed occurrence passes.
  - The report shows file and line.
- **tests**:
  - **e2e**:
    - A PR adding a hard-coded 'ITP' label fails the lint job.
  - **integration**:
    - Run over a fixture directory: 2 findings with the expected line numbers.
    - The coverage endpoint returns the same findings.
  - **unit**:
    - Scanner flags 'Raise NCR' in a template and returns a suggested key.
    - A string inside an allow-list entry is skipped.
