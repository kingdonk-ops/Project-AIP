# ARCH-02 — Module registry and dependency check

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Load manifests at boot, mount only enabled modules and fail fast on bad dependencies.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/src/platform/modules/registry.ts
  - apps/api/src/platform/modules/registry.spec.ts
  - apps/api/src/app.module.ts
- **steps**:
  - 1. Glob modules/*/manifest.json and validate each with ModuleManifest.
  - 2. Topologically sort by dependsOn. Throw on an unknown dependency or a cycle, naming the modules involved.
  - 3. Mount each module's Nest module dynamically in the sorted order.
  - 4. Expose GET /api/v1/platform/modules, which returns the id, context and dependencies of each module and feeds the generated module map.
  - 5. Write tools/gen-module-map.ts, which produces docs/architecture/module-map.md from the registry.
- **acceptance**:
  - A manifest with dependsOn:['ghost'] stops boot with the error 'module a depends on unknown module ghost'.
  - A cycle a->b->a stops boot and the error names both modules.
  - Module-map output is deterministic: two runs give an identical file.
- **tests**:
  - **e2e**:
    - Boot the API with a deliberately broken fixture manifest. Expected: the process exits non-zero within 10s and the log contains the module id.
  - **integration**:
    - Boot the API with 3 fixture modules. GET /api/v1/platform/modules returns exactly 3 entries in dependency order.
    - Run gen-module-map twice and diff the output. Expected: no difference.
  - **unit**:
    - Sort of {a:[b], b:[]} gives [b,a].
    - Sort of {a:[b], b:[a]} throws CycleError containing 'a' and 'b'.
    - Unknown dependency throws MissingDependencyError('ghost').
