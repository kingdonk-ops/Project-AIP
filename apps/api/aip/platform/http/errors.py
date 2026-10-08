"""FastAPI exception handlers for the database helper errors (DATABASE-04).

``ConflictError`` becomes 409 ``{"code": "VERSION_CONFLICT", "current": {...}}`` so the client can
show a field diff; ``NotFoundError`` becomes 404 ``{"code": "NOT_FOUND"}`` (also what a row of
another tenant looks like, since RLS hides it); ``CycleError`` becomes 422 ``PATH_CYCLE``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from aip.platform.db.errors import ConflictError, CycleError, NotFoundError

__all__ = ["install_error_handlers"]


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        body = {"code": "VERSION_CONFLICT", "current": exc.current}
        return JSONResponse(jsonable_encoder(body), status_code=409)

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"code": "NOT_FOUND"}, status_code=404)

    @app.exception_handler(CycleError)
    async def cycle(request: Request, exc: CycleError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        return JSONResponse({"code": "PATH_CYCLE"}, status_code=422)
