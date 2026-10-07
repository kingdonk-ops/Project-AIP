# ARCH-04 — Request context carrying tenant, project, actor and asset scope
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
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (`with_tenant(ctx)` consumes this context), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (job payloads carry `tenant_id`), [0005](../../docs/adr/0005-identity-architecture.md) (sessions are resolved server-side; tenant resolved before login), [0004](../../docs/adr/0004-repository-layout.md)

## Spec

Provide one context object, held in a `contextvars.ContextVar`, that every service, repository, event writer and job reads.

- **depends on**:
  - ARCH-01
- **files**:
  - apps/api/aip/platform/context/__init__.py
  - apps/api/aip/platform/context/context.py
  - apps/api/aip/platform/context/middleware.py
  - apps/api/aip/platform/context/resolvers.py (`PrincipalResolver`, `ProjectMembershipResolver` protocols)
  - apps/api/aip/platform/jobs/context.py (`tenant_job` decorator)
  - apps/api/tests/platform/context/test_context.py
  - apps/api/tests/platform/context/test_middleware.py
- **steps**:
  - 1. Define `RequestContext` (frozen dataclass): `tenant_id: UUID`, `project_id: UUID | None`, `actor_id: UUID | None`, `asset_path_scope: tuple[str, ...]` (ltree paths), `request_id: str`. Store it in a module-level `ContextVar[RequestContext]`.
  - 2. `get_context()` returns the current context or raises `ContextMissingError`. `use_context(ctx)` is a context manager (sync and async) that sets the var and resets the token on exit. `run_with_context(ctx, fn, *args)` awaits `fn` inside `use_context`, for jobs and tests.
  - 3. Write a pure ASGI middleware (not `BaseHTTPMiddleware`, so the var propagates to the endpoint) that: reads or generates `X-Request-Id`; asks the injected `PrincipalResolver` for the verified principal (tenant, actor, asset scope) — the session/cookie implementation arrives with identity tasks (ADR 0005), tests inject a fixture resolver mapping test bearer tokens to principals; if `X-Project-Id` is present, asks the injected `ProjectMembershipResolver` and returns 403 when the actor is not a member; sets the context; echoes `X-Request-Id` on the response.
  - 4. `tenant_job` decorator for job handlers: reads `tenant_id` (and optional `actor_id`, `request_id`) from the job kwargs and runs the handler inside `use_context`. A payload without `tenant_id` raises `ContextMissingError` before the handler runs.
  - 5. Add a test-only route `GET /api/v1/_debug/context` (mounted only when `AIP_ENV=test`) that returns the current context as JSON.
- **acceptance**:
  - Context survives `await`, `asyncio.gather`, `asyncio.create_task`, `loop.call_later` and `anyio.to_thread.run_sync` (sync FastAPI dependencies).
  - Two concurrent requests never see each other's `tenant_id`.
  - Calling `get_context()` outside a scope raises `ContextMissingError`.
- **tests**:
  - **unit**:
    - `await run_with_context(RequestContext(tenant_id=T1, ...), coro)` where `coro` does `await asyncio.sleep(0.005); return get_context().tenant_id` returns `T1`.
    - `get_context()` with no scope raises `ContextMissingError`.
    - `asyncio.gather` of 50 `run_with_context` calls with distinct tenant ids returns each call's own id, in order.
    - A `tenant_job`-wrapped handler called with `{"tenant_id": str(T1)}` sees `get_context().tenant_id == T1`; called with `{}` raises `ContextMissingError` without running the body.
  - **integration**:
    - Fixture tenants `tenant-a` and `tenant-b` (UUIDs defined in `tests/conftest.py`). Send two simultaneous requests via `httpx.AsyncClient` with tokens for A and B to `/api/v1/_debug/context`. Expected: the responses echo A and B respectively.
    - Send `X-Project-Id` for a project the fixture membership resolver says the user is not a member of. Expected: 403.
  - **e2e**:
    - Start the API with the fixture resolver (`AIP_ENV=test`), call an authenticated endpoint as the `tenant-a` fixture user. Expected: the response has an `X-Request-Id` header and the in-memory audit sink fixture records `tenant_id` = tenant-a's id with the same request id.
