"""The OIDC callback's success step: issue the app session and redirect (IDENTITY-03 step 8).

``session_login_handler(request)`` is the default ``ExternalLoginHandler``: JIT provisioning
(IDENTITY-02), then ``issue_session`` in the user's tenant with ``aal`` from ``derive_aal``,
the ID token's ``amr``, ``auth_time`` and ``sid``, the client IP and user agent, and the sid
presented with the login (revoked as ``rotated``). The answer is 303 to the validated same-origin
``returnTo`` with the two ``__Host-`` cookies set; no token reaches the browser.

IDENTITY-04: ``aal`` also counts the upstream IdP's ``amr`` for a brokered sign-in, the session
records ``identity.session_amr``, and the first ``aal=2`` session stamps ``mfa_enrolled_at``.

IDENTITY-10: ``portal_login_handler(request)`` is the portal callback's handler: the same JIT
provisioning (which refuses anyone but a ``portal`` user for the portal audience), then a session
with ``audience="portal"`` and only the portal cookies (``__Host-aip_portal_sid`` /
``__Host-aip_portal_csrf``). A sign-in below aal 2 is refused (403 ``MFA_NOT_SATISFIED``).
"""

from __future__ import annotations

from typing import Literal

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from aip.modules.identity import repository as repo
from aip.modules.identity.jit import JitLoginHandler, Provisioned
from aip.modules.identity.oidc import safe_return_to
from aip.modules.identity.schemas import VerifiedExternalIdentity
from aip.modules.identity.session_store import read_sid
from aip.modules.identity.sessions import issue_session, set_session_cookies
from aip.platform.db.session import with_tenant

__all__ = ["portal_login_handler", "session_login_handler"]


def _handler(request: Request, audience: Literal["app", "portal"]) -> JitLoginHandler:
    presented = read_sid(request.headers, audience)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    async def on_success(identity: VerifiedExternalIdentity, result: Provisioned) -> Response:
        aal = identity.aal
        if audience == "portal" and (aal != 2 or identity.audience != "portal"):
            return JSONResponse(
                {"code": "MFA_NOT_SATISFIED", "detail": "a second factor is required"},
                status_code=403,
            )
        async with with_tenant(result.tenant_id) as conn:
            user = await repo.get_user(conn, result.user_id)
            user_class = user.user_class if user is not None else "staff"
            issued = await issue_session(
                conn,
                user_id=result.user_id,
                user_class=user_class,
                aal=aal,
                amr=identity.session_amr,
                authenticated_at=identity.auth_time,
                kc_sid=identity.kc_sid,
                audience=audience,
                ip=ip,
                user_agent=user_agent,
                presented_sid=presented,
            )
            if aal == 2:
                await repo.mark_mfa_enrolled(conn, result.user_id)
        response = RedirectResponse(safe_return_to(identity.return_to), status_code=303)
        set_session_cookies(response, issued)
        return response

    return JitLoginHandler(on_success=on_success)


def session_login_handler(request: Request) -> JitLoginHandler:
    """The staff callback's handler (``aip-api``, ``audience="app"``)."""
    return _handler(request, "app")


def portal_login_handler(request: Request) -> JitLoginHandler:
    """The portal callback's handler (``aip-portal``, ``audience="portal"``)."""
    return _handler(request, "portal")
