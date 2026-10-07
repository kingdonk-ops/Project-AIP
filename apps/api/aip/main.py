"""FastAPI application factory.

Run with: ``uvicorn aip.main:create_app --factory``

At boot the module registry (ARCH-02) loads every module manifest and mounts the enabled modules'
routers under ``/api/v1`` in dependency order. ``AIP_MODULES_PACKAGE`` overrides the package that
holds the modules and ``AIP_DISABLED_MODULES`` (comma-separated) skips modules. Any registry
error propagates, so a bad module set stops the process from starting.
"""

from collections.abc import Iterable

from fastapi import APIRouter, FastAPI

from aip.platform.modules.registry import load_modules
from aip.platform.modules.routes import create_router as create_modules_router


def create_app(
    modules_package: str | None = None, disabled_modules: Iterable[str] | None = None
) -> FastAPI:
    modules = load_modules(modules_package, disabled_modules)

    app = FastAPI(title="AIP API", version="0.1.0")

    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/health", tags=["platform"])
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    v1.include_router(create_modules_router(modules))
    for module in modules:
        v1.include_router(module.router)

    app.include_router(v1)
    app.state.modules = modules
    return app
