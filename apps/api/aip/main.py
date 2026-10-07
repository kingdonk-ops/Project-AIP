"""FastAPI application factory.

Run with: ``uvicorn aip.main:create_app --factory``
"""

import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from aip.platform.context import (
    ContextMissingError,
    DenyAllMembershipResolver,
    DenyAllPrincipalResolver,
    PrincipalResolver,
    ProjectMembershipResolver,
    RequestContextMiddleware,
    get_context,
)


def create_app(
    *,
    principal_resolver: PrincipalResolver | None = None,
    membership_resolver: ProjectMembershipResolver | None = None,
    env: str | None = None,
) -> FastAPI:
    env = os.environ.get("AIP_ENV", "") if env is None else env
    app = FastAPI(title="AIP API", version="0.1.0")

    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/health", tags=["platform"])
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

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

    app.include_router(v1)

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
    return app
