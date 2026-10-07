# ARCH-02 — Module registry and dependency check
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
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md), [0004](../../docs/adr/0004-repository-layout.md)

## Spec

Load module manifests at boot, mount only enabled modules' routers in dependency order and fail fast on bad dependencies.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/aip/platform/modules/registry.py
  - apps/api/aip/platform/modules/routes.py (`GET /api/v1/platform/modules`)
  - apps/api/aip/main.py (call the registry from `create_app()`)
  - apps/api/tests/platform/modules/test_registry.py
  - apps/api/tests/platform/modules/fixtures/ (fixture module packages: `ok_a`, `ok_b`, `ok_c`, `ghost_dep`, `cycle_a`, `cycle_b`)
  - tools/gen_module_map.py
  - docs/architecture/module-map.md (generated)
- **steps**:
  - 1. `discover(package: str = "aip.modules") -> list[LoadedModule]` finds every sub-package with a `manifest.toml` (skipping `_template`), validates it with `ModuleManifest` and imports the package. The package root is injectable so tests can point at the fixtures.
  - 2. `sort_modules(manifests) -> list[str]`: topological sort on `depends_on` with alphabetical tie-break so the order is deterministic. Raise `MissingDependencyError` (message `module a depends on unknown module ghost`) or `CycleError` (message names every module in the cycle).
  - 3. In `create_app()`, include each module's `routes.router` in sorted order under `/api/v1`. A module listed in `AIP_DISABLED_MODULES` (comma-separated) is skipped, and skipping a module that another enabled module depends on raises `MissingDependencyError`. Any registry error aborts startup (the uvicorn process exits non-zero).
  - 4. `GET /api/v1/platform/modules` returns `[{id, context, depends_on}]` in mount order (Pydantic response model, so it appears in OpenAPI).
  - 5. `tools/gen_module_map.py` writes `docs/architecture/module-map.md` from the registry: a table of modules plus a Mermaid `graph TD` of dependencies, sorted, with no timestamps, so the output is byte-stable.
- **acceptance**:
  - A manifest with `depends_on = ["ghost"]` stops boot with the error `module a depends on unknown module ghost`.
  - A cycle a → b → a stops boot and the error names both modules.
  - Module-map output is deterministic: two runs give an identical file.
- **tests**:
  - **unit**:
    - `sort_modules({"a": ["b"], "b": []})` returns `["b", "a"]`.
    - `sort_modules({"a": ["b"], "b": ["a"]})` raises `CycleError` whose message contains `a` and `b`.
    - `sort_modules({"a": ["ghost"]})` raises `MissingDependencyError` with `ghost` in the message.
    - `sort_modules({"c": [], "a": [], "b": []})` returns `["a", "b", "c"]`.
  - **integration**:
    - `create_app(modules_package="tests.platform.modules.fixtures.ok")` with fixtures `ok_a` (depends on `ok_b`), `ok_b` (depends on `ok_c`), `ok_c`; `GET /api/v1/platform/modules` via `httpx.AsyncClient` returns exactly 3 entries in order `ok_c, ok_b, ok_a`.
    - Run `python tools/gen_module_map.py` twice and diff the output. Expected: no difference.
  - **e2e**:
    - Start uvicorn with `AIP_MODULES_PACKAGE` pointing at the `ghost_dep` fixture. Expected: the process exits non-zero within 10 s and stderr contains `ghost_dep`.
