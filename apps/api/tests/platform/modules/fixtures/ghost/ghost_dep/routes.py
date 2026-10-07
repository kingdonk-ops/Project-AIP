"""Routes for fixture module ghost_dep."""

from fastapi import APIRouter

router = APIRouter(prefix="/ghost_dep", tags=["ghost_dep"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "ghost_dep"}
