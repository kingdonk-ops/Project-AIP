"""HTTP routes for item_types (ITEMTYPES-01), mounted under ``/api/v1``.

Every route declares its permission with ``requires(...)`` (deny by default, ACCESS-01) and needs
an active tenant. Reading anything needs ``item_type.view``; categories and item types are edited
with ``item_type.edit``; content types are managed with ``item_type.manage``. Explicit
``operation_id``s keep the generated client's hook names stable.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from aip.modules.item_types.schemas import (
    CategoryCreate,
    CategoryOut,
    CategoryPage,
    CategoryUpdate,
    ContentTypeCreate,
    ContentTypeOrder,
    ContentTypeOut,
    ContentTypePage,
    ContentTypeUpdate,
    FieldTypesOut,
    ItemTypeCreate,
    ItemTypeErrorBody,
    ItemTypeOut,
    ItemTypePage,
    ItemTypeUpdate,
)
from aip.modules.item_types.service import (
    CategoryService,
    ContentTypeService,
    ItemTypeService,
    field_registry,
)
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import requires

__all__ = ["router"]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ItemTypeErrorBody}}
_CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ItemTypeErrorBody}}
# The 422 description is pinned so the schema is stable across Python versions: FastAPI
# otherwise fills it from HTTPStatus(422).phrase, which 3.13 renamed to "Unprocessable Content".
_INVALID: dict[int | str, dict[str, Any]] = {
    422: {"model": ItemTypeErrorBody, "description": "Unprocessable Entity"}
}

Search = Annotated[str | None, Query(min_length=1, max_length=100)]

field_types_router = APIRouter(prefix="/field-types", tags=["item_types"])
content_types_router = APIRouter(prefix="/content-types", tags=["item_types"])
categories_router = APIRouter(prefix="/item-categories", tags=["item_types"])
item_types_router = APIRouter(prefix="/item-types", tags=["item_types"])


# --- field-type registry ----------------------------------------------------------------------


@field_types_router.get(
    "",
    operation_id="item_types_field_types",
    response_model=FieldTypesOut,
    dependencies=[Depends(requires("item_type.view"))],
)
async def get_field_types() -> FieldTypesOut:
    return field_registry()


# --- content types ----------------------------------------------------------------------------


@content_types_router.get(
    "",
    operation_id="item_types_content_types_list",
    response_model=ContentTypePage,
    dependencies=[Depends(requires("item_type.view"))],
)
async def list_content_types(
    show_in_nav: Annotated[bool | None, Query(alias="showInNav")] = None,
) -> ContentTypePage:
    return await ContentTypeService().list(show_in_nav=show_in_nav)


@content_types_router.put(
    "/order",
    operation_id="item_types_content_types_order",
    response_model=ContentTypePage,
    responses=_INVALID,
    dependencies=[Depends(requires("item_type.manage"))],
)
async def order_content_types(body: ContentTypeOrder) -> ContentTypePage:
    return await ContentTypeService().reorder(body.ids)


@content_types_router.get(
    "/{content_type_id}",
    operation_id="item_types_content_types_get",
    response_model=ContentTypeOut,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("item_type.view"))],
)
async def get_content_type(content_type_id: UUID) -> ContentTypeOut:
    return await ContentTypeService().get(content_type_id)


@content_types_router.post(
    "",
    operation_id="item_types_content_types_create",
    response_model=ContentTypeOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("item_type.manage"))],
)
async def create_content_type(body: ContentTypeCreate) -> ContentTypeOut:
    return await ContentTypeService().create(body)


@content_types_router.patch(
    "/{content_type_id}",
    operation_id="item_types_content_types_update",
    response_model=ContentTypeOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("item_type.manage"))],
)
async def update_content_type(content_type_id: UUID, body: ContentTypeUpdate) -> ContentTypeOut:
    return await ContentTypeService().update(content_type_id, body)


@content_types_router.delete(
    "/{content_type_id}",
    operation_id="item_types_content_types_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("item_type.manage"))],
)
async def delete_content_type(content_type_id: UUID) -> Response:
    await ContentTypeService().delete(content_type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- item categories --------------------------------------------------------------------------


@categories_router.get(
    "",
    operation_id="item_types_categories_list",
    response_model=CategoryPage,
    dependencies=[Depends(requires("item_type.view"))],
)
async def list_categories(
    content_type_id: Annotated[UUID, Query(alias="contentTypeId")],
) -> CategoryPage:
    return await CategoryService().list(content_type_id=content_type_id)


@categories_router.get(
    "/{category_id}",
    operation_id="item_types_categories_get",
    response_model=CategoryOut,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("item_type.view"))],
)
async def get_category(category_id: UUID) -> CategoryOut:
    return await CategoryService().get(category_id)


@categories_router.post(
    "",
    operation_id="item_types_categories_create",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("item_type.edit"))],
)
async def create_category(body: CategoryCreate) -> CategoryOut:
    return await CategoryService().create(body)


@categories_router.patch(
    "/{category_id}",
    operation_id="item_types_categories_update",
    response_model=CategoryOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("item_type.edit"))],
)
async def update_category(category_id: UUID, body: CategoryUpdate) -> CategoryOut:
    return await CategoryService().update(category_id, body)


@categories_router.delete(
    "/{category_id}",
    operation_id="item_types_categories_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("item_type.edit"))],
)
async def delete_category(category_id: UUID) -> Response:
    await CategoryService().delete(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- item types -------------------------------------------------------------------------------


@item_types_router.get(
    "",
    operation_id="item_types_item_types_list",
    response_model=ItemTypePage,
    dependencies=[Depends(requires("item_type.view"))],
)
async def list_item_types(
    content_type_id: Annotated[UUID | None, Query(alias="contentTypeId")] = None,
    category_id: Annotated[UUID | None, Query(alias="categoryId")] = None,
    q: Search = None,
) -> ItemTypePage:
    return await ItemTypeService().list(
        content_type_id=content_type_id, category_id=category_id, q=q
    )


@item_types_router.get(
    "/{item_type_id}",
    operation_id="item_types_item_types_get",
    response_model=ItemTypeOut,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("item_type.view"))],
)
async def get_item_type(item_type_id: UUID) -> ItemTypeOut:
    return await ItemTypeService().get(item_type_id)


@item_types_router.post(
    "",
    operation_id="item_types_item_types_create",
    response_model=ItemTypeOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("item_type.edit"))],
)
async def create_item_type(body: ItemTypeCreate) -> ItemTypeOut:
    return await ItemTypeService().create(body)


@item_types_router.patch(
    "/{item_type_id}",
    operation_id="item_types_item_types_update",
    response_model=ItemTypeOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("item_type.edit"))],
)
async def update_item_type(item_type_id: UUID, body: ItemTypeUpdate) -> ItemTypeOut:
    return await ItemTypeService().update(item_type_id, body)


@item_types_router.delete(
    "/{item_type_id}",
    operation_id="item_types_item_types_delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("item_type.edit"))],
)
async def delete_item_type(item_type_id: UUID) -> Response:
    await ItemTypeService().delete(item_type_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


router = APIRouter(dependencies=[Depends(require_active_tenant)])
router.include_router(field_types_router)
router.include_router(content_types_router)
router.include_router(categories_router)
router.include_router(item_types_router)
