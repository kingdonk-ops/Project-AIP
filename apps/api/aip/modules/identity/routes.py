"""HTTP routes for identity (IDENTITY-01).

- ``POST /api/v1/auth/login/start``: public, rate limited (10/min per IP).
- ``GET /api/v1/auth/oidc/callback``: public; clears the pre-auth cookie on every outcome.

Both carry the ``x-aip-access: public`` OpenAPI marker, a no-op declaration until ACCESS-01
reads it. Error bodies are ``{code, detail}`` and never contain a token, email or tenant.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.responses import Response

from aip.modules.identity import preauth_cookie
from aip.modules.identity.api import ExternalLoginHandler, get_external_login_handler
from aip.modules.identity.oidc import KeycloakOidcClient, OidcError
from aip.modules.identity.repository import SqlLoginDirectory
from aip.modules.identity.schemas import ErrorResponse, LoginStartRequest, LoginStartResponse
from aip.modules.identity.service import LoginRateLimiter, LoginService
from aip.modules.identity.settings import IdentitySettings, IdentitySettingsError

logger = logging.getLogger(__name__)

PUBLIC: dict[str, Any] = {"x-aip-access": "public"}

router = APIRouter(prefix="/auth", tags=["identity"])


@lru_cache(maxsize=1)
def _settings() -> IdentitySettings:
    return IdentitySettings()  # pyright: ignore[reportCallIssue] - values come from the environment


def get_identity_settings() -> IdentitySettings:
    try:
        return _settings()
    except (ValidationError, IdentitySettingsError):
        logger.error("identity settings are missing or invalid; sign-in is unavailable")
        raise HTTPException(status_code=503, detail="sign-in is not configured") from None


def get_login_service(
    request: Request, settings: Annotated[IdentitySettings, Depends(get_identity_settings)]
) -> LoginService:
    service: LoginService | None = getattr(request.app.state, "identity_login_service", None)
    if service is None:
        oidc = KeycloakOidcClient(
            issuer=settings.issuer,
            token_endpoint=settings.token_endpoint,
            jwks_uri=settings.jwks_uri,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret.get_secret_value(),
            redirect_uri=settings.redirect_uri,
            jwks_ttl=settings.jwks_ttl_seconds,
            timeout=settings.http_timeout_seconds,
        )
        service = LoginService(settings, SqlLoginDirectory(), oidc)
        request.app.state.identity_login_service = service
    return service


def get_login_rate_limiter(request: Request) -> LoginRateLimiter:
    limiter: LoginRateLimiter | None = getattr(request.app.state, "identity_rate_limiter", None)
    if limiter is None:
        limiter = LoginRateLimiter.from_redis_url(os.environ.get("REDIS_URL"))
        request.app.state.identity_rate_limiter = limiter
    return limiter


def _error(code: str, status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status_code)


@router.post(
    "/login/start",
    response_model=LoginStartResponse,
    responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    openapi_extra=PUBLIC,
)
async def login_start(
    body: LoginStartRequest,
    request: Request,
    service: Annotated[LoginService, Depends(get_login_service)],
    limiter: Annotated[LoginRateLimiter, Depends(get_login_rate_limiter)],
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if not await limiter.hit(client_ip):
        return _error("RATE_LIMITED", 429, "too many sign-in attempts; try again shortly")
    try:
        start = await service.start(body.email, body.return_to)
    except ValueError:
        return _error("INVALID_EMAIL", 422, "enter a valid email address")
    response = JSONResponse(start.response.model_dump(mode="json", by_alias=True))
    preauth_cookie.set_cookie(response, start.sealed_cookie)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/oidc/callback",
    responses={400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    openapi_extra=PUBLIC,
)
async def oidc_callback(
    request: Request,
    service: Annotated[LoginService, Depends(get_login_service)],
    handler: Annotated[ExternalLoginHandler, Depends(get_external_login_handler)],
) -> Response:
    cookie = request.cookies.get(preauth_cookie.COOKIE_NAME)
    try:
        identity = await service.complete(dict(request.query_params), cookie)
    except OidcError as exc:
        logger.info("oidc callback refused: %s", exc.code)
        response: Response = _error(exc.code, exc.status_code, exc.message)
    else:
        response = await handler(identity)
    preauth_cookie.clear_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    return response
