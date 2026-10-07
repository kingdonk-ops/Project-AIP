"""Routes for fixture module ok_b."""

from fastapi import APIRouter

router = APIRouter(prefix="/ok_b", tags=["ok_b"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ok_b"}
