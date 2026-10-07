"""FastAPI application factory.

Run with: ``uvicorn aip.main:create_app --factory``

At boot the module registry (ARCH-02) loads every module manifest and mounts the enabled modules'
routers under ``/api/v1`` in dependency order. ``AIP_MODULES_PACKAGE`` overrides the package that
holds the modules and ``AIP_DISABLED_MODULES`` (comma-separated) skips modules. Any registry
error propagates, so a bad module set stops the process from starting.

Every request passes through the request-context middleware (ARCH-04), which resolves the
principal and project membership; the default resolvers deny everyone.

Observability (OPS-04): ``RequestIdMiddleware`` is the outermost middleware (request id, JSON
request log line); logs are JSON on stdout with the PII scrubber; OpenTelemetry tracing starts when
``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. ``/api/v1/health/live`` and ``/api/v1/health/ready`` come
from ``aip.modules.ops.health`` and are mounted here, outside the module registry.
"""

import os
from collections.abc import Iterable

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from aip.modules.ops.health import ReadinessChecker
from aip.modules.ops.health import router as health_router
from aip.platform.context import (
    ContextMissingError,
    DenyAllMembershipResolver,
    DenyAllPrincipalResolver,
    PrincipalResolver,
    ProjectMembershipResolver,
    RequestContextMiddleware,
    get_context,
)
from aip.platform.modules.registry import load_modules
from aip.platform.modules.routes import create_router as create_modules_router
from aip.platform.observability.logging import RequestIdMiddleware, configure_logging
from aip.platform.observability.otel import init_tracing


def create_app(
    modules_package: str | None = None,
    disabled_modules: Iterable[str] | None = None,
    *,
    principal_resolver: PrincipalResolver | None = None,
    membership_resolver: ProjectMembershipResolver | None = None,
    env: str | None = None,
    readiness: ReadinessChecker | None = None,
    tracing: bool = True,
) -> FastAPI:
    configure_logging()
    modules = load_modules(modules_package, disabled_modules)
    env = os.environ.get("AIP_ENV", "") if env is None else env

    app = FastAPI(title="AIP API", version="0.1.0")

    app.state.readiness = readiness or ReadinessChecker.from_env()

    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(health_router)

    if env == "test":
        # ARCH-04: test-only echo of the request context. Never mounted outside AIP_ENV=test.
        @v1.get("/_debug/context", include_in_schema=False)
        async def debug_context() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
            ctx = get_context()
            return {
                "tenant_id": str(ctx.tenant_id),
                "project_id": None if ctx.project_id is None else str(ctx.project_id),
                "actor_id": None if ctx.actor_id is None else str(ctx.actor_id),
                "asset_path_scope": list(ctx.asset_path_scope),
                "request_id": ctx.request_id,
            }

    v1.include_router(create_modules_router(modules))
    for module in modules:
        v1.include_router(module.router)

    app.include_router(v1)
    app.state.modules = modules

    @app.exception_handler(ContextMissingError)
    async def context_missing(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: ContextMissingError
    ) -> JSONResponse:
        # A request reached code that needs a tenant context but no principal was resolved.
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    app.add_middleware(
        RequestContextMiddleware,
        principal_resolver=principal_resolver or DenyAllPrincipalResolver(),
        membership_resolver=membership_resolver or DenyAllMembershipResolver(),
    )
    # Added last, so it runs first: the request id exists before the context is resolved.
    app.add_middleware(RequestIdMiddleware)
    if tracing:
        app.state.tracing = init_tracing(app)
    return app
