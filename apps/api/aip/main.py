"""FastAPI application factory.

Run with: ``uvicorn aip.main:create_app --factory``
"""

from fastapi import APIRouter, FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AIP API", version="0.1.0")

    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/health", tags=["platform"])
    def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    app.include_router(v1)
    return app
