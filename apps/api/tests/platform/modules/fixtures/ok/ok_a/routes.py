"""Routes for fixture module ok_a."""

from fastapi import APIRouter

router = APIRouter(prefix="/ok_a", tags=["ok_a"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ok_a"}
