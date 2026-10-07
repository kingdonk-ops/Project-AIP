"""``GET /api/v1/platform/modules``: the mounted modules in mount order (ARCH-02)."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from aip.platform.modules.registry import LoadedModule


class ModuleInfo(BaseModel):
    """A mounted module as reported by the registry."""

    model_config = ConfigDict(frozen=True)

    id: str
    context: str
    depends_on: list[str]


def create_router(modules: Sequence[LoadedModule]) -> APIRouter:
    """Build the platform modules router for an app's resolved module list."""
    infos = [
        ModuleInfo(
            id=module.id,
            context=module.manifest.context,
            depends_on=list(module.manifest.depends_on),
        )
        for module in modules
    ]
    router = APIRouter(prefix="/platform/modules", tags=["platform"])

    @router.get("", response_model=list[ModuleInfo])
    def list_modules() -> list[ModuleInfo]:  # pyright: ignore[reportUnusedFunction]
        return infos

    return router
