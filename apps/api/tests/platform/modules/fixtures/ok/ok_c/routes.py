"""Routes for fixture module ok_c."""

from fastapi import APIRouter, Depends

from aip.platform.access import public

router = APIRouter(prefix="/ok_c", tags=["ok_c"], dependencies=[Depends(public())])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ok_c"}
