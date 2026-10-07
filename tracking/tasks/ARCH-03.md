# ARCH-03 — Import-boundary lint and manifest CI check
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (import-linter rules, ESLint boundaries, rejected paths), [0001](../../docs/adr/0001-greenfield-python-backend.md) (import-linter replaces dependency-cruiser), [0002](../../docs/adr/0002-data-access-and-migrations.md)

## Spec

Make module isolation and the ADR 0004 layout a required CI gate: import-linter for the Python API, ESLint boundaries for the TypeScript apps, and a manifest check.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/pyproject.toml (`[tool.importlinter]` contracts)
  - tools/ci/importlinter_contracts.py (custom contract type `module_public_api`)
  - tools/ci/check_manifests.py
  - tools/ci/check_layout.py
  - packages/config-eslint/index.js (shared ESLint config with `eslint-plugin-boundaries`)
  - .github/workflows/ci.yml
  - apps/api/tests/arch/test_import_contracts.py
  - apps/api/tests/arch/test_check_manifests.py
  - apps/api/tests/arch/test_check_layout.py
  - apps/api/tests/arch/fixtures/ (`deep_import/` package with its own `.importlinter`, `platform_imports_module/`, `undeclared_event/`, `clean/`)
- **steps**:
  - 1. Write the custom import-linter contract `module_public_api` (contract name `no-deep-module-import`): for any import from `aip.modules.<x>.*` to `aip.modules.<y>.*` with x ≠ y, the target must be `aip.modules.<y>` or `aip.modules.<y>.api`. Report each violation as `importer -> imported`.
  - 2. Add a `forbidden` contract `platform-never-imports-modules`: `aip.platform` may not import `aip.modules`.
  - 3. In `packages/config-eslint`, configure boundaries so `apps/*` never import other `apps/*` and may import only `packages/*` (including the generated `packages/api-client`). Every app's ESLint config extends it.
  - 4. `tools/ci/check_manifests.py` parses each module's Python files with `ast` and collects string-literal first arguments of `require_permission(...)`, `emit(...)` (second argument: event name) and `term(...)`. Each must appear in that module's `manifest.toml` (`permissions`, `events`, `term_keys`). Output one error per missing item, exit 1 if any.
  - 5. `tools/ci/check_layout.py` fails on any top-level `backend/`, `frontend/` or `services/` path, any `*.ts`, `*.tsx` or `package.json` under `apps/api/`, and any `*.py` under `packages/` (ADR 0004 consequence).
  - 6. Wire `lint-imports`, `check_manifests.py`, `check_layout.py` and `pnpm -r lint` into `.github/workflows/ci.yml` as a `boundaries` job and mark it required in the branch-protection notes of the PR.
  - 7. Add fixture packages that violate each rule, used only by the tests and excluded from the real contracts.
- **acceptance**:
  - Importing `aip.modules.b.service` from module a fails `lint-imports` naming `no-deep-module-import`.
  - Importing `aip.modules.b.api` (or `from aip.modules import b`) passes.
  - A permission string used in code but absent from the manifest fails `check_manifests.py`.
  - Adding `backend/x.py` or `apps/api/foo.ts` fails `check_layout.py`.
- **tests**:
  - **unit**:
    - `check_manifests` on the `undeclared_event` fixture (code calls `emit(conn, "x.y.z", 1, ...)`, manifest has no events) returns exactly one error naming `x.y.z`.
    - `check_manifests` on the `clean` fixture returns an empty list.
    - `check_layout` on a file list `["services/sidecar/main.py"]` returns one error naming `services/`.
  - **integration**:
    - Run `lint-imports --config apps/api/tests/arch/fixtures/deep_import/.importlinter`. Expected: exit 1 and exactly one broken contract, `no-deep-module-import`.
    - Run `lint-imports --config apps/api/tests/arch/fixtures/platform_imports_module/.importlinter`. Expected: exit 1, contract `platform-never-imports-modules` broken.
    - Run `uv run lint-imports` on the real repo. Expected: exit 0.
    - Add `import x from "../../web/src/main"` in a temp file under `apps/portal/src`; `pnpm --filter portal lint`. Expected: non-zero with a boundaries error.
  - **e2e**:
    - Open a throwaway PR that adds a deep import. Expected: the `boundaries` CI job fails and the merge is blocked.
