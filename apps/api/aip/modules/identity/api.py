"""Published interface of the identity module.

Other modules may import only this file. Keep it small and stable.

``ExternalLoginHandler`` receives the ``VerifiedExternalIdentity`` at the end of the OIDC callback
and turns it into the HTTP response. IDENTITY-01 ships a placeholder; IDENTITY-02 replaces it with
JIT provisioning and IDENTITY-03 with session issue, by overriding the
``get_external_login_handler`` dependency.
"""

from __future__ import annotations

import os
from typing import Protocol

from starlette.responses import JSONResponse, Response

from aip.modules.identity.schemas import VerifiedExternalIdentity

__all__ = [
    "ExternalLoginHandler",
    "ModuleApi",
    "PlaceholderLoginHandler",
    "VerifiedExternalIdentity",
    "get_api",
    "get_external_login_handler",
]


class ExternalLoginHandler(Protocol):
    async def __call__(self, identity: VerifiedExternalIdentity) -> Response: ...


class PlaceholderLoginHandler:
    """``AIP_ENV=test``: echo the identity as JSON. Elsewhere: 501 PROVISIONING_NOT_IMPLEMENTED."""

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
    """FastAPI dependency; later tasks override it (``app.dependency_overrides``)."""
    return PlaceholderLoginHandler()


class ModuleApi(Protocol):
    """The operations identity offers to other modules."""


def get_api() -> ModuleApi:
    """Return the identity module's published interface."""
    raise NotImplementedError
