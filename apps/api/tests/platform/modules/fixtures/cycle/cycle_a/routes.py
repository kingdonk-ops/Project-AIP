"""Routes for fixture module cycle_a."""

from fastapi import APIRouter

router = APIRouter(prefix="/cycle_a", tags=["cycle_a"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "cycle_a"}
