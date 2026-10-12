"""Routes for fixture module ok_a."""

from fastapi import APIRouter, Depends

from aip.platform.access import public

router = APIRouter(prefix="/ok_a", tags=["ok_a"], dependencies=[Depends(public())])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ok_a"}
