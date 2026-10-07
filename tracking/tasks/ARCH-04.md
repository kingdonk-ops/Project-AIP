# ARCH-04 — Request context carrying tenant, project, actor and asset scope

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

Provide one context object read by every service, repository and event writer.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/src/platform/context/context.ts
  - apps/api/src/platform/context/context.middleware.ts
  - apps/api/src/platform/context/context.spec.ts
- **steps**:
  - 1. Define RequestContext {tenantId, projectId?, actorId?, assetPathScope: string[] (ltree paths), requestId} held in AsyncLocalStorage.
  - 2. Write middleware that fills the context from verified claims, and from the X-Project-Id header only after checking membership via an injectable resolver.
  - 3. Add getContext(), which throws ContextMissingError when called outside a request.
  - 4. Add runWithContext(ctx, fn) for workers and tests.
  - 5. Make the worker call runWithContext using the tenant_id on the job or event.
- **acceptance**:
  - Context survives async hops (await, Promise.all, setTimeout).
  - Two concurrent requests never see each other's tenantId.
  - Calling getContext() outside a scope throws.
- **tests**:
  - **e2e**:
    - Log in as a Kaefer user and call an authenticated endpoint. Expected: the response header X-Request-Id is present and the audit stub records the same tenant_id.
  - **integration**:
    - Send two simultaneous HTTP requests with tokens for tenants A and B to /api/v1/_debug/context. Expected: the responses echo A and B respectively.
    - Send X-Project-Id for a project the user is not a member of. Expected: 403.
  - **unit**:
    - runWithContext({tenantId:'t1'}, async()=>{await sleep(5); return getContext().tenantId}) returns 't1'.
    - getContext() with no scope throws ContextMissingError.
    - 50 parallel runWithContext calls with distinct tenant ids each return their own id.
