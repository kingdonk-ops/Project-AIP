"""Routes for the ACCESS-01 fixture module."""

from fastapi import APIRouter, Depends

from aip.platform.access import requires

router = APIRouter(prefix="/fixture", tags=["fixture"])


@router.get("/items", dependencies=[Depends(requires("fixture.item.read"))])
async def list_items() -> dict[str, list[str]]:
    return {"items": []}
