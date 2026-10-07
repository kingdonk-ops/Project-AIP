"""Routes for fixture module cycle_b."""

from fastapi import APIRouter

router = APIRouter(prefix="/cycle_b", tags=["cycle_b"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "cycle_b"}
