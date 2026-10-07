# STACK-03 — Generated typed API client with drift check

| Field | Value |
|---|---|
| Module | [`stack`](../../docs/blueprint/modules/stack/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/stack/README.md`](../../docs/blueprint/modules/stack/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Keep the Next.js frontend type-safe against the API's OpenAPI schema.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/src/openapi.ts
  - packages/api-client/orval.config.ts
  - packages/api-client/src/generated/
  - tools/ci/check-client-drift.sh
- **steps**:
  - 1. Export the OpenAPI JSON from NestJS to packages/api-client/openapi.json via a script.
  - 2. Configure orval to generate the TanStack Query client from that schema.
  - 3. Mark generated files as read-only (header comment plus a CI check against hand edits).
  - 4. check-client-drift regenerates the client and fails if git diff is non-empty.
  - 5. Make apps/web build against the generated client.
- **acceptance**:
  - Changing a DTO without regenerating fails CI.
  - Generated code is never hand-edited.
  - apps/web builds against the current schema.
- **tests**:
  - **e2e**:
    - Call a generated hook in a Next.js test page against the running API. Expected: it renders typed data with no runtime shape errors.
  - **integration**:
    - Run drift check on a clean tree. Expected: exit 0.
    - Add a field to a DTO and run drift check. Expected: exit 1 and the diff names the field.
    - Run pnpm --filter web build. Expected: 0 type errors.
  - **unit**:
    - The OpenAPI export script produces valid JSON containing the path /api/v1/health.
