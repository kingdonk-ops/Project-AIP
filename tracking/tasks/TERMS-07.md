# TERMS-07 — Hard-coded string linter and coverage report
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0004](../../docs/adr/0004-repository-layout.md) (`packages/config-eslint`, "no hard-coded UI strings" ESLint rule, `config/terms/en-AU/`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Fail CI on raw labels such as ITP, NCR or Variation in backend templates, API label fields and frontend JSX, and expose the findings in an admin coverage report.

- **depends on**:
  - TERMS-01
- **files**:
  - apps/api/aip/modules/terms/lint.py
  - apps/api/aip/modules/terms/routes.py (coverage endpoint)
  - apps/api/aip/modules/terms/schemas.py
  - apps/api/aip/modules/terms/manifest.toml
  - apps/api/aip/modules/terms/tests/test_lint.py
  - apps/api/aip/modules/terms/tests/fixtures/lint/
  - config/terms/lint-allowlist.toml
  - packages/config-eslint/rules/no-hardcoded-labels.js
  - packages/config-eslint/rules/no-hardcoded-labels.test.ts
  - .github/workflows/ci.yml
- **steps**:
  - 1. `lint.py` (`python -m aip.modules.terms.lint --out terms-lint-findings.json`) builds a deny-list from the default texts in `config/terms/en-AU/*.json` (whole-word, case-sensitive for abbreviations such as ITP, NCR, MEWP; case-insensitive for words such as Variation). It scans Jinja email and PDF templates (`apps/api/aip/**/templates/**/*.j2`, text nodes only, not `{{ }}`/`{% %}` expressions) and, with Python `ast`, string literals assigned to Pydantic fields named `label`, `title` or `display_name` (defaults and `Literal[...]` values) in `apps/api/aip/**/schemas.py`.
  - 2. Add `config/terms/lint-allowlist.toml`: entries `{path, line_pattern, term, reason}`; an entry without a `reason` is itself a finding.
  - 3. Produce findings JSON: a list of `{file, line, column, term, suggested_key}`, where `suggested_key` is the dictionary key whose default text matches. Exit 1 when the list is non-empty.
  - 4. Add the ESLint rule `no-hardcoded-labels` in `packages/config-eslint` that flags JSX text and string literals in `aria-label`, `title`, `placeholder` and `label` props that match the same deny-list (read from `config/terms/en-AU/*.json` at lint start). Enable it in the shared config for `apps/web`, `apps/field`, `apps/portal` and `packages/ui`.
  - 5. Run both in CI (`.github/workflows/ci.yml`: a `terms-lint` job running the Python scanner and `pnpm -r lint`). Upload `terms-lint-findings.json` as a build artifact and copy it into the API image at `aip/modules/terms/data/lint_findings.json`.
  - 6. `GET /api/v1/terms/coverage` (`requires('terms.coverage.read')`, declared in `manifest.toml`) returns the findings baked into the running build with the build commit, as a Pydantic response model.
- **acceptance**:
  - A literal 'NCR' in a template fails CI.
  - An allow-listed occurrence passes.
  - The report shows file and line.
- **tests** (pytest for the scanner and endpoint; Vitest `RuleTester` for the ESLint rule):
  - **e2e**:
    - A PR adding a hard-coded `<span>ITP</span>` in `apps/web` fails the lint job (verified once on a throwaway branch and recorded in the PR).
  - **integration**:
    - Run the scanner over `tests/fixtures/lint/` (one `.j2` template with "Raise NCR" on line 3, one `schemas.py` with `label: str = "Variation"` on line 7). Expected: 2 findings with exactly those files and lines.
    - With the fixture findings file in place, `GET /api/v1/terms/coverage` as a principal granted `terms.coverage.read` returns the same 2 findings; without the grant it returns 403.
  - **unit**:
    - The scanner flags `Raise NCR` in a template line and returns `suggested_key = 'record.type.ncr'`.
    - A string matched by an allow-list entry is skipped.
    - `RuleTester`: `<span>NCR</span>` is invalid; `<span>{t('record.type.ncr')}</span>` is valid.
