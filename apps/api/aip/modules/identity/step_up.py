"""MFA enforcement and step-up for critical actions (IDENTITY-04 step 6, ADR 0005 rev 2, ADR 0010).

Every login's session ``aal`` comes from ``derive_aal``: local accounts always reach ``aal2`` (the
realm flow requires a second factor), brokered accounts reach it only when the customer IdP's
``amr`` reports one (``upstream_amr``). An ``aal1`` session may do ordinary work but never a
critical action.

- ``check_step_up`` (pure): the session has ``aal == 2`` and authenticated within
  ``max_age_min`` minutes.
- ``step_up(max_age_min=None)``: FastAPI dependency for critical routes. The default window is the
  tenant's ``tenant_auth_policy.step_up_max_age_min`` (10 without a row). Refusal is 401
  ``{"detail": {"code": "STEP_UP_REQUIRED", "message", "stepUpUrl"}}``.
- ``build_step_up_url`` (pure): Keycloak's authorize URL with ``prompt=login``, ``max_age=0``,
  ``acr_values=aal2`` and ``login_hint``, plus ``kc_idp_hint`` for SSO users (the IdPs forward
  ``prompt`` and ``max_age`` so the customer IdP re-authenticates too).
- ``check_step_up_callback`` (pure) and ``complete_step_up``: the callback for a step-up sign-in
  requires the same Keycloak subject as the session's user (``STEP_UP_SUBJECT_MISMATCH``), a sign-in
  no older than the step-up start (``STEP_UP_STALE``) and a second factor (``MFA_NOT_SATISFIED``);
  only then is the session rotated with ``aal=2`` and the new ``authenticated_at``. A refusal
  leaves the session unchanged.

``now()`` honours ``AIP_TEST_CLOCK_OFFSET`` (seconds) only when ``AIP_ENV`` is ``test`` or
``development``, so e2e tests can age a session past the window.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Final
from urllib.parse import quote, urlsplit
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.responses import JSONResponse, RedirectResponse, Response

from aip.modules.identity import repository as repo
from aip.modules.identity.oidc import OidcError, build_authorize_url, safe_return_to
from aip.modules.identity.principal import Principal, get_principal
from aip.modules.identity.schemas import VerifiedExternalIdentity
from aip.modules.identity.session_store import current_session
from aip.modules.identity.sessions import rotate_session, set_session_cookies
from aip.platform.db.session import with_tenant

__all__ = [
    "DEFAULT_MAX_AGE_MIN",
    "STEP_UP_PARAMS",
    "STEP_UP_START_PATH",
    "StepUpRequiredError",
    "build_step_up_url",
    "check_step_up",
    "check_step_up_callback",
    "complete_step_up",
    "now",
    "require_step_up",
    "step_up",
    "step_up_url",
    "tenant_max_age_min",
]

logger = logging.getLogger(__name__)

STEP_UP_START_PATH: Final = "/api/v1/auth/step-up/start"
DEFAULT_MAX_AGE_MIN: Final = 10
STEP_UP_PARAMS: Final = {"prompt": "login", "max_age": "0", "acr_values": "aal2"}
_CLOCK_ENVS: Final = frozenset({"test", "development"})
# Keycloak's and the API's clocks may differ by a little; a step-up is minutes, not seconds.
STEP_UP_CLOCK_LEEWAY: Final = timedelta(seconds=5)


def now() -> datetime:
    """The step-up clock: UTC now, shifted by ``AIP_TEST_CLOCK_OFFSET`` in test/dev only."""
    current = datetime.now(UTC)
    if os.environ.get("AIP_ENV", "") in _CLOCK_ENVS:
        raw = os.environ.get("AIP_TEST_CLOCK_OFFSET", "").strip()
        if raw:
            try:
                current += timedelta(seconds=float(raw))
            except ValueError:
                logger.warning("AIP_TEST_CLOCK_OFFSET is not a number; ignored")
    return current


def check_step_up(
    *, aal: int, authenticated_at: datetime | None, now: datetime, max_age_min: int
) -> bool:
    """True when a second factor was used within the last ``max_age_min`` minutes."""
    if aal < 2 or authenticated_at is None:
        return False
    return now - authenticated_at <= timedelta(minutes=max_age_min)


def step_up_url(return_to: str | None) -> str:
    return f"{STEP_UP_START_PATH}?returnTo={quote(safe_return_to(return_to), safe='/')}"


class StepUpRequiredError(HTTPException):
    """401 ``STEP_UP_REQUIRED`` with the URL that starts the step-up."""

    def __init__(self, return_to: str | None) -> None:
        super().__init__(
            status_code=401,
            detail={
                "code": "STEP_UP_REQUIRED",
                "message": "confirm it is you with your second factor to continue",
                "stepUpUrl": step_up_url(return_to),
            },
        )


def build_step_up_url(
    *,
    email: str,
    idp_alias: str | None,
    authorize_endpoint: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_verifier: str,
) -> str:
    """Keycloak's authorize URL that forces a fresh sign-in with a second factor."""
    return build_authorize_url(
        authorize_endpoint=authorize_endpoint,
        client_id=client_id,
        redirect_uri=redirect_uri,
        email=email,
        idp_alias=idp_alias,
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
        extra_params=STEP_UP_PARAMS,
    )


def check_step_up_callback(
    *,
    expected_subject: UUID | None,
    subject: str,
    auth_time: datetime,
    started_at: datetime,
    aal: int,
) -> None:
    """``OidcError`` (403) unless this sign-in is a fresh second factor by the session's user."""
    if expected_subject is None or subject != str(expected_subject):
        raise OidcError(
            "STEP_UP_SUBJECT_MISMATCH", 403, "the confirmation was made by a different account"
        )
    if auth_time < started_at - STEP_UP_CLOCK_LEEWAY:
        raise OidcError("STEP_UP_STALE", 403, "the confirmation did not sign in again")
    if aal < 2:
        raise OidcError("MFA_NOT_SATISFIED", 403, "a second factor is required")


_MAX_AGE = text(
    "SELECT step_up_max_age_min FROM tenant_auth_policy WHERE deleted_at IS NULL"
    " AND tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
)


async def tenant_max_age_min(conn: AsyncConnection) -> int:
    """The bound tenant's step-up window in minutes (``DEFAULT_MAX_AGE_MIN`` without a row)."""
    value = (await conn.execute(_MAX_AGE)).scalar_one_or_none()
    return int(value) if value is not None else DEFAULT_MAX_AGE_MIN


def _return_to(request: Request) -> str:
    """Where the browser should come back to: the same-origin page that made the request."""
    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        origin = os.environ.get("APP_ORIGIN", "")
        if origin and f"{parts.scheme}://{parts.netloc}" == origin.rstrip("/"):
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            return safe_return_to(path)
    return "/"


async def require_step_up(
    request: Request,
    principal: Principal,
    *,
    max_age_min: int | None = None,
    conn: AsyncConnection | None = None,
) -> None:
    """Raise ``StepUpRequiredError`` unless ``principal`` passes ``check_step_up``.

    Inside a route that already holds the tenant's connection, pass it as ``conn``.
    """
    window = max_age_min
    if window is None:
        if conn is not None:
            window = await tenant_max_age_min(conn)
        else:
            async with with_tenant(principal.tenant_id) as own:
                window = await tenant_max_age_min(own)
    if not check_step_up(
        aal=principal.aal,
        authenticated_at=principal.authenticated_at,
        now=now(),
        max_age_min=window,
    ):
        raise StepUpRequiredError(_return_to(request))


def step_up(max_age_min: int | None = None) -> Callable[..., Awaitable[None]]:
    """FastAPI dependency for critical actions: ``dependencies=[Depends(step_up())]``."""

    async def dependency(
        request: Request, principal: Annotated[Principal, Depends(get_principal)]
    ) -> None:
        await require_step_up(request, principal, max_age_min=max_age_min)

    return dependency


def _refusal(code: str, status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"code": code, "detail": detail}, status_code=status_code)


async def complete_step_up(identity: VerifiedExternalIdentity) -> Response:
    """The OIDC callback for ``purpose='step_up'``: rotate the session to ``aal=2`` or refuse."""
    state = identity.step_up
    session = current_session()
    if state is None or session is None or session.session_id != state.session_id:
        logger.info("step-up refused: STEP_UP_SESSION_MISMATCH")
        return _refusal(
            "STEP_UP_SESSION_MISMATCH", 403, "start the confirmation again from the app"
        )
    async with with_tenant(session.tenant_id) as conn:
        user = await repo.get_user(conn, session.user_id)
        aal = identity.aal
        try:
            check_step_up_callback(
                expected_subject=user.keycloak_user_id if user is not None else None,
                subject=identity.subject,
                auth_time=identity.auth_time,
                started_at=state.started_at,
                aal=aal,
            )
        except OidcError as exc:
            await repo.record_auth_event(
                conn,
                tenant_id=session.tenant_id,
                event_type="step_up.denied",
                user_id=session.user_id,
                detail={"reason": exc.code.lower()},
            )
            logger.info("step-up refused: %s", exc.code)
            return _refusal(exc.code, exc.status_code, exc.message)
        issued = await rotate_session(
            conn,
            session.session_id,
            aal=aal,
            amr=identity.session_amr,
            authenticated_at=identity.auth_time,
        )
        await repo.mark_mfa_enrolled(conn, session.user_id)
        await repo.record_auth_event(
            conn,
            tenant_id=session.tenant_id,
            event_type="step_up.succeeded",
            user_id=session.user_id,
            detail={"amr": identity.session_amr},
        )
    response = RedirectResponse(safe_return_to(identity.return_to), status_code=303)
    set_session_cookies(response, issued)
    return response
