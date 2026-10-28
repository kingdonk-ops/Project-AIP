"""The sealed pre-authentication cookie ``__Host-aip_preauth`` (IDENTITY-01).

Between ``POST /auth/login/start`` and the OIDC callback the backend keeps state, nonce, the PKCE
code verifier, the resolved tenant and IdP alias and a same-origin ``returnTo``. They travel in one
cookie encrypted with JWE (``alg=dir``, ``enc=A256GCM``, key ``PREAUTH_COOKIE_KEY``), so the browser
can neither read nor change them. It lives 10 minutes and is cleared on every callback outcome.

IDENTITY-04: a step-up (``GET /auth/step-up/start``) seals the same cookie with
``purpose='step_up'``, the session being elevated and when the step-up started (epoch seconds);
the callback then checks the new sign-in against them instead of provisioning a login.

IDENTITY-10: ``audience`` (``app`` or ``portal``) seals which sign-in flow started, so a portal
cookie cannot finish at the staff callback or the reverse.
"""

from __future__ import annotations

import json
import time
from typing import Literal
from uuid import UUID

from joserfc import jwe
from joserfc.errors import JoseError
from joserfc.jwk import OctKey
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.responses import Response

__all__ = [
    "COOKIE_NAME",
    "MAX_AGE_SECONDS",
    "InvalidPreAuthError",
    "PreAuthState",
    "clear_cookie",
    "open_cookie",
    "seal",
    "set_cookie",
]

COOKIE_NAME = "__Host-aip_preauth"
MAX_AGE_SECONDS = 600
_HEADER = {"alg": "dir", "enc": "A256GCM"}
_ALGORITHMS = ["dir", "A256GCM"]


class InvalidPreAuthError(Exception):
    """The cookie is missing, tampered with, expired or unreadable."""


class PreAuthState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str
    nonce: str
    code_verifier: str
    tenant_id: UUID | None
    idp_alias: str | None
    return_to: str
    exp: int
    purpose: Literal["login", "step_up"] = "login"
    audience: Literal["app", "portal"] = "app"

    session_id: UUID | None = None
    started_at: int | None = None


def new_expiry(now: float | None = None) -> int:
    return int(now if now is not None else time.time()) + MAX_AGE_SECONDS


def seal(state: PreAuthState, key: bytes) -> str:
    payload = state.model_dump_json().encode("utf-8")
    return jwe.encrypt_compact(_HEADER, payload, OctKey.import_key(key), algorithms=_ALGORITHMS)


def open_cookie(value: str | None, key: bytes, *, now: float | None = None) -> PreAuthState:
    if not value:
        raise InvalidPreAuthError("no pre-auth cookie")
    try:
        obj = jwe.decrypt_compact(value, OctKey.import_key(key), algorithms=_ALGORITHMS)
        if obj.protected.get("alg") != "dir" or obj.protected.get("enc") != "A256GCM":
            raise InvalidPreAuthError("unexpected JWE header")
        state = PreAuthState.model_validate(json.loads(obj.plaintext or b""))
    except (JoseError, ValueError, ValidationError, TypeError) as exc:
        raise InvalidPreAuthError("unreadable pre-auth cookie") from exc
    if state.exp < int(now if now is not None else time.time()):
        raise InvalidPreAuthError("expired pre-auth cookie")
    return state


def set_cookie(response: Response, value: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=MAX_AGE_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
