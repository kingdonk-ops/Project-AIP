"""Routes for fixture module ghost_dep."""

from fastapi import APIRouter, Depends

from aip.platform.access import public

router = APIRouter(prefix="/ghost_dep", tags=["ghost_dep"], dependencies=[Depends(public())])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ghost_dep"}
