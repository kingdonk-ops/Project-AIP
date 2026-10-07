"""Routes for fixture module ok_c."""

from fastapi import APIRouter

router = APIRouter(prefix="/ok_c", tags=["ok_c"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ok_c"}
