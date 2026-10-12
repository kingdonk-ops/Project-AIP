"""Routes for fixture module cycle_a."""

from fastapi import APIRouter, Depends

from aip.platform.access import public

router = APIRouter(prefix="/cycle_a", tags=["cycle_a"], dependencies=[Depends(public())])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "cycle_a"}
