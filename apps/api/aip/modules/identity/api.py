"""Published interface of the identity module.

Other modules may import only this file. Keep it small and stable.

``ExternalLoginHandler`` receives the ``VerifiedExternalIdentity`` at the end of the OIDC callback
and turns it into the HTTP response. IDENTITY-01 shipped a placeholder; IDENTITY-02 makes
``JitLoginHandler`` (just-in-time provisioning, ``jit.py``) the default, and IDENTITY-03 passes
its session issue as the handler's ``on_success``. Tests and later tasks can still replace the
handler by overriding the ``get_external_login_handler`` dependency.

Users (IDENTITY-02): ``get_user``, ``list_users``, ``find_by_email``, ``set_user_status`` and
``record_auth_event`` all take the connection from ``with_tenant`` and see only that tenant.
``Principal``, ``PrincipalResolver`` and the ``get_principal`` dependency describe the caller.
"""

from __future__ import annotations

import os
from typing import Protocol

from starlette.responses import JSONResponse, Response

from aip.modules.identity.jit import JitLoginHandler
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
    find_by_email,
    get_user,
    list_users,
    record_auth_event,
    set_user_status,
)
from aip.modules.identity.schemas import VerifiedExternalIdentity

__all__ = [
    "ExternalLoginHandler",
    "JitLoginHandler",
    "ModuleApi",
    "PlaceholderLoginHandler",
    "PlatformPrincipalAdapter",
    "Principal",
    "PrincipalResolver",
    "UserPage",
    "UserRow",
    "VerifiedExternalIdentity",
    "find_by_email",
    "get_api",
    "get_external_login_handler",
    "get_principal",
    "get_user",
    "list_users",
    "record_auth_event",
    "set_user_status",
    "stub_principal_resolver",
]


class ExternalLoginHandler(Protocol):
    async def __call__(self, identity: VerifiedExternalIdentity) -> Response: ...


class PlaceholderLoginHandler:
    """``AIP_ENV=test``: echo the identity as JSON. Elsewhere: 501 PROVISIONING_NOT_IMPLEMENTED.

    IDENTITY-01's handler, kept for the sign-in flow tests that check the verified identity.
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


def get_external_login_handler() -> ExternalLoginHandler:
    """FastAPI dependency: JIT provisioning (IDENTITY-02). Overridable via dependency_overrides."""
    return JitLoginHandler()


class ModuleApi(Protocol):
    """The operations identity offers to other modules."""


def get_api() -> ModuleApi:
    """Return the identity module's published interface."""
    raise NotImplementedError
