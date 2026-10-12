"""Routes for the ACCESS-01 fixture module: one route without an access declaration."""

from fastapi import APIRouter

router = APIRouter(prefix="/fixture", tags=["fixture"])


@router.get("/unguarded")
async def unguarded() -> dict[str, str]:
    return {"leak": "yes"}
