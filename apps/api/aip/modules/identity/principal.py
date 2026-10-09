"""The authenticated principal and how a request gets one (IDENTITY-02, ADR 0005).

- ``Principal``: who is calling, for which tenant, at which assurance level (Pydantic v2,
  camelCase JSON). ``tenant_id`` and ``user_id`` must be non-nil UUIDs.
- ``PrincipalResolver``: the port that turns request headers into a ``Principal`` (or ``None``).
  IDENTITY-03's session cookie dependency and IDENTITY-06's bearer dependency implement it.
- ``get_principal``: FastAPI dependency. 401 when there is no principal, or when the principal
  does not match the request context the context middleware built from the same resolver.
- ``PlatformPrincipalAdapter``: hands the identity resolver to the platform's request-context
  middleware (``aip.platform.context``), which only needs the tenant and the actor.

Until IDENTITY-03, ``StubHeaderPrincipalResolver`` reads the ``x-test-principal`` header (the
``Principal`` as JSON). It works only when ``AIP_ENV=test`` and ``AUTH_TEST_STUB=1``, both checked
at app start (``stub_principal_resolver``) and again on every request. ``create_app`` refuses to
start with ``AUTH_TEST_STUB`` set in production (``RuntimeError('test auth stub forbidden in
production')``) or in any environment other than ``test``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic.alias_generators import to_camel

from aip.platform.context import ContextMissingError, get_context
from aip.platform.context import Principal as ContextPrincipal

__all__ = [
    "TEST_PRINCIPAL_HEADER",
    "DenyAllResolver",
    "PlatformPrincipalAdapter",
    "Principal",
    "PrincipalResolver",
    "StubHeaderPrincipalResolver",
    "get_principal",
    "stub_auth_enabled",
    "stub_principal_resolver",
]

logger = logging.getLogger(__name__)

TEST_PRINCIPAL_HEADER = "x-test-principal"
_MAX_TEST_HEADER = 4096

UserClass = Literal["staff", "field", "portal"]


class Principal(BaseModel):
    """A verified caller. Built only by a ``PrincipalResolver``, never from request data."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True
    )

    kind: Literal["user"]
    tenant_id: UUID
    user_id: UUID
    user_class: UserClass
    session_id: UUID | None = None
    aal: Literal[1, 2]
    amr: list[str] = Field(default_factory=list[str], max_length=16)

    @field_validator("tenant_id", "user_id")
    @classmethod
    def _not_nil(cls, value: UUID) -> UUID:
        if value.int == 0:
            raise ValueError("must not be the nil UUID")
        return value


@runtime_checkable
class PrincipalResolver(Protocol):
    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        """The verified principal for these (lower-cased) request headers, or ``None``."""
        ...


class DenyAllResolver:
    """No principal for anyone: the default until IDENTITY-03 wires sessions."""

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        return None


def _stub_flag() -> str:
    return os.environ.get("AUTH_TEST_STUB", "").strip()


def stub_auth_enabled() -> bool:
    """True only when ``AIP_ENV=test`` and ``AUTH_TEST_STUB=1`` (read from the environment now)."""
    return os.environ.get("AIP_ENV", "") == "test" and _stub_flag() == "1"


class StubHeaderPrincipalResolver:
    """Test-only: the ``x-test-principal`` header as a ``Principal``. See the module docstring."""

    def __init__(self) -> None:
        if not stub_auth_enabled():
            raise RuntimeError("test auth stub needs AIP_ENV=test and AUTH_TEST_STUB=1")

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        if not stub_auth_enabled():  # the environment changed after start: fail closed
            return None
        raw = headers.get(TEST_PRINCIPAL_HEADER)
        if not raw or len(raw) > _MAX_TEST_HEADER:
            return None
        try:
            return Principal.model_validate_json(raw)
        except ValidationError:
            return None


def stub_principal_resolver(env: str) -> StubHeaderPrincipalResolver | None:
    """The test resolver when the stub is on, else ``None``; refuses the stub outside test.

    Any non-empty ``AUTH_TEST_STUB`` other than ``0`` counts as set for the refusal, so a typo
    cannot slip a stub into production; only exactly ``1`` turns it on.
    """
    flag = _stub_flag()
    if flag in ("", "0"):
        return None
    if env == "production" or os.environ.get("AIP_ENV", "") == "production":
        raise RuntimeError("test auth stub forbidden in production")
    if env != "test" or os.environ.get("AIP_ENV", "") != "test" or flag != "1":
        raise RuntimeError("test auth stub is only allowed with AIP_ENV=test and AUTH_TEST_STUB=1")
    logger.warning("AUTH_TEST_STUB=1: the x-test-principal header authenticates requests")
    return StubHeaderPrincipalResolver()


class PlatformPrincipalAdapter:
    """The identity resolver as the platform middleware's ``PrincipalResolver``."""

    def __init__(self, resolver: PrincipalResolver) -> None:
        self._resolver = resolver

    async def resolve(self, headers: Mapping[str, str]) -> ContextPrincipal | None:
        principal = await self._resolver.resolve(headers)
        if principal is None:
            return None
        return ContextPrincipal(tenant_id=principal.tenant_id, actor_id=principal.user_id)


_NOT_AUTHENTICATED = {"code": "NOT_AUTHENTICATED", "message": "not authenticated"}


def _unauthenticated() -> HTTPException:
    return HTTPException(status_code=401, detail=dict(_NOT_AUTHENTICATED))


def principal_resolver_of(request: Request) -> PrincipalResolver:
    resolver: PrincipalResolver | None = getattr(
        request.app.state, "identity_principal_resolver", None
    )
    return resolver if resolver is not None else DenyAllResolver()


async def get_principal(request: Request) -> Principal:
    """FastAPI dependency: the caller's ``Principal`` or 401 ``NOT_AUTHENTICATED``.

    The principal must agree with the request context (same tenant and actor), so a route can
    never run with a principal for one tenant and an RLS context for another.
    """
    principal = await principal_resolver_of(request).resolve(request.headers)
    if principal is None:
        raise _unauthenticated()
    try:
        ctx = get_context()
    except ContextMissingError:
        raise _unauthenticated() from None
    if ctx.tenant_id != principal.tenant_id or ctx.actor_id != principal.user_id:
        logger.warning("principal does not match the request context; refusing")
        raise _unauthenticated()
    return principal
