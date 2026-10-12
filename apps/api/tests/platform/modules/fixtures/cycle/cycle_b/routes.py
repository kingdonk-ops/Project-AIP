"""Routes for fixture module cycle_b."""

from fastapi import APIRouter, Depends

from aip.platform.access import public

router = APIRouter(prefix="/cycle_b", tags=["cycle_b"], dependencies=[Depends(public())])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "cycle_b"}
