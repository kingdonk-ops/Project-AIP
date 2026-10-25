"""HTTP routes for the asset tree (ASSETS-01), mounted under ``/api/v1/assets``.

Every route declares its permission with ``requires(...)`` (deny by default, ACCESS-01) and needs
an active tenant. Explicit ``operation_id``s keep the generated client's hook names stable. The
tree is accessible by permission and tenant only; asset-subtree scope predicates arrive with
ASSETS-07.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Response, status

from aip.modules.assets.schemas import (
    AssetCreate,
    AssetDetail,
    AssetErrorBody,
    AssetMove,
    AssetOut,
    AssetPage,
    AssetSort,
    AssetUpdate,
)
from aip.modules.assets.service import AssetService
from aip.modules.assets.settings import get_settings
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import requires

__all__ = ["router"]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": AssetErrorBody}}
_CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": AssetErrorBody}}
_INVALID: dict[int | str, dict[str, Any]] = {422: {"description": "Validation error"}}

Limit = Annotated[int, Query(ge=1, le=200)]
Cursor = Annotated[str | None, Query(max_length=1024)]
Search = Annotated[str | None, Query(min_length=1, max_length=100)]

assets_router = APIRouter(prefix="/assets", tags=["assets"])


@assets_router.get(
    "",
    operation_id="assets_list",
    response_model=AssetPage,
    responses=_INVALID,
    dependencies=[Depends(requires("asset.view"))],
)
async def list_assets(
    limit: Limit = 50,
    cursor: Cursor = None,
    sort: AssetSort | None = None,
    parent_id: Annotated[str | None, Query(alias="parentId", max_length=36)] = None,
    under: UUID | None = None,
    q: Search = None,
    tag_number: Annotated[str | None, Query(alias="tagNumber", min_length=1, max_length=64)] = None,
) -> AssetPage:
    return await AssetService().list(
        limit=limit,
        cursor=cursor,
        sort=sort,
        parent_id=parent_id,
        under=under,
        q=q,
        tag_number=tag_number,
    )


@assets_router.get(
    "/{asset_id}",
    operation_id="assets_get",
    response_model=AssetDetail,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("asset.view"))],
)
async def get_asset(asset_id: UUID) -> AssetDetail:
    return await AssetService().get(asset_id)


@assets_router.post(
    "",
    operation_id="assets_create",
    response_model=AssetOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": AssetOut}, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("asset.create"))],
)
async def create_asset(body: AssetCreate, response: Response) -> AssetOut:
    asset, created = await AssetService().create(body)
    if not created:  # an idempotent replay returns the first row with 200
        response.status_code = status.HTTP_200_OK
    return asset


@assets_router.patch(
    "/{asset_id}",
    operation_id="assets_update",
    response_model=AssetOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("asset.update"))],
)
async def update_asset(asset_id: UUID, body: AssetUpdate) -> AssetOut:
    return await AssetService().update(asset_id, body)


@assets_router.post(
    "/{asset_id}/move",
    operation_id="assets_move",
    response_model=AssetOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("asset.move"))],
)
async def move_asset(asset_id: UUID, body: AssetMove) -> AssetOut:
    return await AssetService().move(asset_id, body)


@assets_router.delete(
    "/{asset_id}",
    operation_id="assets_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("asset.delete"))],
)
async def delete_asset(
    asset_id: UUID, sync_version: Annotated[int, Query(alias="syncVersion", ge=1)]
) -> Response:
    await AssetService().delete(asset_id, sync_version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@asynccontextmanager
async def _validate_settings(app: FastAPI) -> AsyncIterator[None]:
    """Load the settings when the server starts, so a missing cursor key fails the deploy."""
    get_settings()
    yield


router = APIRouter(dependencies=[Depends(require_active_tenant)], lifespan=_validate_settings)
router.include_router(assets_router)
