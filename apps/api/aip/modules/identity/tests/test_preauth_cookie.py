"""The sealed pre-auth cookie (IDENTITY-01 step 5)."""

from __future__ import annotations

import os
from uuid import UUID

import pytest
from starlette.responses import Response

from aip.modules.identity.preauth_cookie import (
    COOKIE_NAME,
    InvalidPreAuthError,
    PreAuthState,
    clear_cookie,
    new_expiry,
    open_cookie,
    seal,
    set_cookie,
)

KEY = os.urandom(32)


def _state(**overrides: object) -> PreAuthState:
    data: dict[str, object] = {
        "state": "s" * 43,
        "nonce": "n" * 43,
        "code_verifier": "v" * 86,
        "tenant_id": UUID("00000000-0000-4000-8000-00000000000a"),
        "idp_alias": "kaefer-oidc",
        "return_to": "/projects",
        "exp": new_expiry(),
    }
    data.update(overrides)
    return PreAuthState.model_validate(data)


def test_round_trip() -> None:
    state = _state()
    sealed = seal(state, KEY)
    assert "kaefer" not in sealed and state.code_verifier not in sealed
    assert open_cookie(sealed, KEY) == state


def test_every_flipped_byte_is_rejected() -> None:
    sealed = seal(_state(), KEY)
    for i in range(0, len(sealed), 7):
        # The last base64url character of a segment can carry unused padding bits: skip it.
        if sealed[i] == "." or i + 1 == len(sealed) or sealed[i + 1] == ".":
            continue
        flipped = sealed[:i] + ("A" if sealed[i] != "A" else "B") + sealed[i + 1 :]
        with pytest.raises(InvalidPreAuthError):
            open_cookie(flipped, KEY)


def test_wrong_key_expired_and_missing() -> None:
    sealed = seal(_state(), KEY)
    with pytest.raises(InvalidPreAuthError):
        open_cookie(sealed, os.urandom(32))
    with pytest.raises(InvalidPreAuthError):
        open_cookie(seal(_state(exp=1), KEY), KEY)
    with pytest.raises(InvalidPreAuthError):
        open_cookie(None, KEY)


def test_cookie_attributes() -> None:
    response = Response()
    set_cookie(response, "v")
    header = response.headers["set-cookie"]
    assert header.startswith(f"{COOKIE_NAME}=v;")
    for attr in ("HttpOnly", "Max-Age=600", "Path=/", "SameSite=lax", "Secure"):
        assert attr in header
    assert "Domain" not in header
    cleared = Response()
    clear_cookie(cleared)
    header = cleared.headers["set-cookie"]
    assert "Max-Age=0" in header and "Secure" in header and "Path=/" in header
