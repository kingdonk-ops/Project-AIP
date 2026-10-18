"""The OIDC callback's success step: issue the app session and redirect (IDENTITY-03 step 8).

``session_login_handler(request)`` is the default ``ExternalLoginHandler``: JIT provisioning
(IDENTITY-02), then ``issue_session`` in the user's tenant with ``aal`` from ``derive_aal``,
the ID token's ``amr``, ``auth_time`` and ``sid``, the client IP and user agent, and the sid
presented with the login (revoked as ``rotated``). The answer is 303 to the validated same-origin
``returnTo`` with the two ``__Host-`` cookies set; no token reaches the browser.

IDENTITY-04: ``aal`` also counts the upstream IdP's ``amr`` for a brokered sign-in, the session
records ``identity.session_amr``, and the first ``aal=2`` session stamps ``mfa_enrolled_at``.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from aip.modules.identity import repository as repo
from aip.modules.identity.jit import JitLoginHandler, Provisioned
from aip.modules.identity.oidc import safe_return_to
from aip.modules.identity.schemas import VerifiedExternalIdentity
from aip.modules.identity.session_store import read_sid
from aip.modules.identity.sessions import issue_session, set_session_cookies
from aip.platform.db.session import with_tenant

__all__ = ["session_login_handler"]


def session_login_handler(request: Request) -> JitLoginHandler:
    presented = read_sid(request.headers)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    async def on_success(identity: VerifiedExternalIdentity, result: Provisioned) -> Response:
        async with with_tenant(result.tenant_id) as conn:
            user = await repo.get_user(conn, result.user_id)
            user_class = user.user_class if user is not None else "staff"
            aal = identity.aal
            issued = await issue_session(
                conn,
                user_id=result.user_id,
                user_class=user_class,
                aal=aal,
                amr=identity.session_amr,
                authenticated_at=identity.auth_time,
                kc_sid=identity.kc_sid,
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
