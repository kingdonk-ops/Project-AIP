# ARCH-01 — Monorepo skeleton and module template

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Create the TypeScript workspace layout and a scaffolded module so every later task has a fixed home.

- **files**:
  - pnpm-workspace.yaml
  - apps/api/src/main.ts
  - apps/api/src/modules/_template/
  - packages/contracts/src/manifest.ts
  - tools/new-module.ts
- **steps**:
  - 1. Create the pnpm workspace with apps/api (NestJS, Node 22), apps/worker, apps/web (Next.js), packages/contracts and services/sidecar (Python, placeholder only).
  - 2. Define the Zod ModuleManifest schema in packages/contracts: id, context, dependsOn[], permissions[], events[], settings[], termKeys[].
  - 3. Build apps/api/src/modules/_template with module.ts, service.ts (the published interface), api.ts (barrel), schemas.ts, events.ts, permissions.ts, manifest.json, controller.ts and tests/.
  - 4. Write tools/new-module.ts to copy the template, substitute the module name and validate the generated manifest.
  - 5. Add a root script that runs build and test across the workspace.
- **acceptance**:
  - pnpm install and pnpm -r build succeed on a clean checkout.
  - Running the scaffolder with name 'widgets' creates a module whose manifest validates and whose empty test passes.
  - The scaffolder refuses names that already exist or are not kebab-case.
- **tests**:
  - **e2e**:
    - Start apps/api with the generated module. GET /api/v1/health returns 200 {status:'ok'}.
  - **integration**:
    - Run the scaffolder for 'widgets', then run pnpm --filter api test. Expected: 1 passing smoke test and exit code 0.
    - Run the scaffolder twice with the same name. Expected: the second run exits 1 and no files change.
  - **unit**:
    - ModuleManifest.parse rejects a manifest missing 'id' and returns a Zod issue at path ['id'].
    - ModuleManifest.parse accepts dependsOn: [] and events: [].
    - Scaffolder name 'Bad Name' exits non-zero with the message 'invalid module name'.
