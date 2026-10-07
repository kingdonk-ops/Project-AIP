# ARCH-01 — Monorepo skeleton and module template
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0004](../../docs/adr/0004-repository-layout.md) (the exact tree this task creates), [0002](../../docs/adr/0002-data-access-and-migrations.md) (where `tables.py` / `repository.py` fit)

## Spec

Create the ADR 0004 repository layout (a uv-managed Python API package and a pnpm workspace for the TypeScript apps) and a scaffolded backend module, so every later task has a fixed home.

- **files**:
  - pyproject.toml (root uv workspace: members `apps/api`; ruff and pyright config)
  - apps/api/pyproject.toml (package `aip`, Python 3.12, FastAPI, Pydantic v2, uvicorn; dev: pytest, pytest-asyncio, httpx, ruff, pyright)
  - apps/api/aip/main.py (FastAPI app factory `create_app()` with `GET /api/v1/health`)
  - apps/api/aip/platform/__init__.py
  - apps/api/aip/platform/modules/manifest.py (Pydantic `ModuleManifest`)
  - apps/api/aip/modules/__init__.py
  - apps/api/aip/modules/_template/ (`__init__.py`, `api.py`, `tables.py`, `schemas.py`, `repository.py`, `service.py`, `policies.py`, `events.py`, `routes.py`, `jobs.py`, `manifest.toml`, `tests/test_smoke.py`)
  - apps/api/tests/test_health.py
  - apps/api/tests/platform/modules/test_manifest.py
  - apps/sandbox/README.md (placeholder; images arrive with UPLOADS/OCR tasks per ADR 0003)
  - pnpm-workspace.yaml, package.json (root, `packageManager` pnpm, `engines.node` 22)
  - apps/web/ (Vite + React + TanStack Router shell: `package.json`, `vite.config.ts`, `src/main.tsx`, `src/routes/__root.tsx`, `src/routes/index.tsx`)
  - apps/field/package.json, apps/portal/package.json (placeholders, no build yet)
  - packages/contracts/package.json, packages/config-ts/tsconfig.base.json
  - tools/new_module.py
  - tools/tests/test_new_module.py
  - Makefile (`make check` = backend + frontend lint, typecheck, test)
- **steps**:
  - 1. Create the uv workspace and `apps/api` package. `uv sync` must install from a committed `uv.lock`. Configure ruff (lint + format) and pyright (`strict` for `aip/platform`, `standard` elsewhere) in the root `pyproject.toml`.
  - 2. `aip/main.py` exposes `create_app() -> FastAPI` with `GET /api/v1/health` returning `{"status": "ok"}`. Run with `uvicorn aip.main:create_app --factory`.
  - 3. Define `ModuleManifest` (Pydantic v2, `extra="forbid"`) loaded from `manifest.toml` via `tomllib`: `id` (snake_case), `context`, `depends_on: list[str]`, `permissions: list[str]`, `events: list[EventRef]` (`name`, `version`), `subscribes: list[EventRef]`, `settings: list[str]`, `term_keys: list[str]`. Add `ModuleManifest.from_toml(path)`.
  - 4. Build `aip/modules/_template/` with the ADR 0004 file set. `__init__.py` re-exports only `api`. `api.py` is the published interface (empty `Protocol` + function stubs). `routes.py` exports `router: APIRouter`. `tests/test_smoke.py` imports the module and asserts its manifest validates. Use the placeholder token `__module__` wherever the name goes.
  - 5. Write `tools/new_module.py <name>`: validates the name against `^[a-z][a-z0-9_]*$` (Python package names; kebab-case is not allowed), refuses an existing folder, copies `_template` to `aip/modules/<name>/`, substitutes `__module__`, then validates the generated manifest. On any failure it removes nothing that existed before and leaves no partial folder.
  - 6. Create the pnpm workspace (`apps/web`, `apps/field`, `apps/portal`, `packages/*`). `apps/web` is a minimal Vite + React + TanStack Router app that renders the terminology key `app.title` placeholder; `apps/field` and `apps/portal` are placeholder packages whose README names the owning tasks.
  - 7. `Makefile` target `check` runs `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest`, `pnpm -r lint`, `pnpm -r typecheck`, `pnpm -r build` and `pnpm -r test`.
- **acceptance**:
  - On a clean checkout, `uv sync --frozen`, `pnpm install --frozen-lockfile` and `make check` succeed.
  - Running `python tools/new_module.py widgets` creates `apps/api/aip/modules/widgets/` whose manifest validates and whose smoke test passes.
  - The scaffolder refuses names that already exist or are not snake_case.
  - There are no `backend/`, `frontend/` or `services/` paths and no TypeScript under `apps/api`.
- **tests**:
  - **unit**:
    - `ModuleManifest.model_validate({})` raises `ValidationError` with an error whose `loc == ("id",)`.
    - `ModuleManifest.model_validate({"id": "x", "context": "platform", "depends_on": [], "events": []})` succeeds.
    - `ModuleManifest.model_validate({..., "colour": "red"})` raises (extra fields forbidden).
    - `python tools/new_module.py "Bad Name"` exits non-zero with the message `invalid module name`.
    - `python tools/new_module.py widgets-x` exits non-zero with `invalid module name` (kebab-case rejected).
  - **integration**:
    - In a temp copy of the repo, run `python tools/new_module.py widgets`, then `uv run pytest apps/api/aip/modules/widgets`. Expected: 1 passed, exit code 0.
    - Run the scaffolder twice with `widgets`. Expected: the second run exits 1 with `module widgets already exists` and `git status --porcelain` shows no change from the second run.
  - **e2e**:
    - Start `uvicorn aip.main:create_app --factory` with the generated module present. `GET /api/v1/health` returns 200 `{"status": "ok"}`.
    - `pnpm --filter web build` produces `apps/web/dist/index.html`.
