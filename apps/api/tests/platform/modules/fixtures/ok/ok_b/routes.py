"""Routes for fixture module ok_b."""

from fastapi import APIRouter, Depends

from aip.platform.access import public

router = APIRouter(prefix="/ok_b", tags=["ok_b"], dependencies=[Depends(public())])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ok_b"}
