"""Published interface of the identity module.

Other modules may import only this file. Keep it small and stable.

``ExternalLoginHandler`` receives the ``VerifiedExternalIdentity`` at the end of the OIDC callback
and turns it into the HTTP response. IDENTITY-01 shipped a placeholder; IDENTITY-02 makes
``JitLoginHandler`` (just-in-time provisioning, ``jit.py``) the default, and IDENTITY-03 passes
its session issue as the handler's ``on_success``. Tests and later tasks can still replace the
handler by overriding the ``get_external_login_handler`` dependency.

Users (IDENTITY-02): ``get_user``, ``list_users``, ``find_by_email``, ``set_user_status`` and
``record_auth_event`` all take the connection from ``with_tenant`` and see only that tenant.
``get_display_names`` (IDENTITY-09) maps user ids to display names for reports and registers.
``ensure_invited_sso_user`` (TESTING-09) pre-creates an invited SSO user for the dev and demo
admin bootstrap (``aip-access bootstrap-admin``).
``Principal``, ``PrincipalResolver`` and the ``get_principal`` dependency describe the caller.

Sessions (IDENTITY-03): ``issue_session``, ``rotate_session`` (IDENTITY-04 step-up),
``revoke_session`` and ``revoke_all_for_user`` (IDENTITY-05 deprovisioning) take the caller's
``with_tenant`` connection. ``add_session_middleware``, ``install_session_errors`` and
``session_resolver`` are the app wiring ``aip.main`` uses.

IDENTITY-04: ``create_invite`` (no step-up; TENANCY-05's first-admin invite) and ``InviteError``;
``step_up`` (the FastAPI dependency critical routes add) and ``require_step_up``; sign-off
assurance (Part D, ADR 0010): ``check_signoff_assurance``, ``derive_assurance``, ``Assurance``,
``SignoffDecision``, ``SignoffContext`` and ``SessionFacts`` (APPROVALS-02 calls it).
APPROVALS-02 also raises ``StepUpRequiredError`` (the 401 ``STEP_UP_REQUIRED`` body, ADR 0034) and
reads ``mfa_enrolled_at`` to know whether a signer could step up.
"""

from __future__ import annotations

import os
from typing import Protocol

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from aip.modules.identity.assurance import (
    Assurance,
    SessionFacts,
    SignoffContext,
    SignoffDecision,
    check_signoff_assurance,
    derive_assurance,
)
from aip.modules.identity.invites import CreatedInvite, InviteError, create_invite
from aip.modules.identity.jit import JitLoginHandler
from aip.modules.identity.login_session import session_login_handler
from aip.modules.identity.principal import (
    PlatformPrincipalAdapter,
    Principal,
    PrincipalResolver,
    get_principal,
    stub_principal_resolver,
)
from aip.modules.identity.repository import (
    UserPage,
    UserRow,
    ensure_invited_sso_user,
    find_by_email,
    get_display_names,
    get_user,
    list_users,
    mfa_enrolled_at,
    record_auth_event,
    set_user_status,
)
from aip.modules.identity.schemas import VerifiedExternalIdentity
from aip.modules.identity.sessions import (
    issue_session,
    revoke_all_for_user,
    revoke_session,
    rotate_session,
)
from aip.modules.identity.step_up import StepUpRequiredError, require_step_up, step_up
from aip.modules.identity.wiring import (
    add_session_middleware,
    install_session_errors,
    session_resolver,
)

__all__ = [
    "Assurance",
    "CreatedInvite",
    "ExternalLoginHandler",
    "InviteError",
    "JitLoginHandler",
    "ModuleApi",
    "PlaceholderLoginHandler",
    "PlatformPrincipalAdapter",
    "Principal",
    "PrincipalResolver",
    "SessionFacts",
    "SignoffContext",
    "SignoffDecision",
    "StepUpRequiredError",
    "UserPage",
    "UserRow",
    "VerifiedExternalIdentity",
    "add_session_middleware",
    "check_signoff_assurance",
    "create_invite",
    "derive_assurance",
    "ensure_invited_sso_user",
    "find_by_email",
    "get_api",
    "get_display_names",
    "get_external_login_handler",
    "get_principal",
    "get_user",
    "install_session_errors",
    "issue_session",
    "list_users",
    "mfa_enrolled_at",
    "record_auth_event",
    "require_step_up",
    "revoke_all_for_user",
    "revoke_session",
    "rotate_session",
    "session_resolver",
    "set_user_status",
    "step_up",
    "stub_principal_resolver",
]


class ExternalLoginHandler(Protocol):
    async def __call__(self, identity: VerifiedExternalIdentity) -> Response: ...


class PlaceholderLoginHandler:
    """``AIP_ENV=test``: echo the identity as JSON. Elsewhere: 501 PROVISIONING_NOT_IMPLEMENTED.

    IDENTITY-01's handler, kept only for the sign-in flow tests that check the verified identity
    (they install it with ``dependency_overrides``); the app uses ``session_login_handler``.
    """

    def __init__(self, env: str | None = None) -> None:
        self._env = os.environ.get("AIP_ENV", "") if env is None else env

    async def __call__(self, identity: VerifiedExternalIdentity) -> Response:
        if self._env == "test":
            return JSONResponse(identity.model_dump(mode="json"))
        return JSONResponse(
            {
                "code": "PROVISIONING_NOT_IMPLEMENTED",
                "detail": "account provisioning is not built yet",
            },
            status_code=501,
        )


def get_external_login_handler(request: Request) -> ExternalLoginHandler:
    """FastAPI dependency: JIT provisioning (IDENTITY-02), then the app session (IDENTITY-03).

    Overridable via ``dependency_overrides``.
    """
    return session_login_handler(request)


class ModuleApi(Protocol):
    """The operations identity offers to other modules."""


def get_api() -> ModuleApi:
    """Return the identity module's published interface."""
    raise NotImplementedError
