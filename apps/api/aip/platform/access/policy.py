"""``PolicyService``: the single, deny-by-default authorisation decision (ACCESS-01).

``can(principal, action, resource=None)`` returns a ``Decision``. In order, failing closed:

1. an action that is not in the catalogue -> ``unknown_permission`` (logged);
2. an inactive principal -> ``inactive_principal``;
3. a resource of another tenant -> ``no_grant``;
4. an ``api_client`` principal (IDENTITY-06) -> allowed exactly when the action is in its scopes;
5. otherwise the union of the registered ``GrantProvider``s' grants: a tenant grant matches any
   resource in the principal's tenant; a project grant matches only a resource with the same
   ``project_id`` (so never a resource without one); any other scope never matches. A provider
   that raises gives ``provider_error`` (logged).

Grants are memoised for the current request only (keyed on the ARCH-04 request context object,
so nothing outlives the request). ACCESS-04 adds a cross-request cache, which may only be keyed by
the tenant's access version (ADR 0020) so a role change applies on the next request.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from aip.platform.access.catalogue import Catalogue
from aip.platform.access.grants import Grant, GrantProvider, ProjectScope, TenantScope
from aip.platform.context import ContextMissingError, RequestContext, get_context

__all__ = [
    "AccessPrincipal",
    "Decision",
    "DecisionReason",
    "Forbidden",
    "PolicyService",
    "Resource",
]

logger = logging.getLogger(__name__)

PrincipalKind = Literal["user", "api_client"]
DecisionReason = Literal[
    "granted", "no_grant", "unknown_permission", "inactive_principal", "provider_error"
]


@dataclass(frozen=True, slots=True)
class AccessPrincipal:
    """Who is asking, as the policy sees it. ``scopes`` only matter for ``api_client``."""

    tenant_id: UUID
    actor_id: UUID | None = None
    kind: PrincipalKind = "user"
    active: bool = True
    scopes: frozenset[str] = field(default_factory=frozenset[str])


@dataclass(frozen=True, slots=True)
class Resource:
    """What is acted on. ``tenant_id`` ``None`` means the principal's tenant (RLS-loaded rows)."""

    project_id: UUID | str | None = None
    tenant_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: DecisionReason
    matched_grant: Grant | None = None


class Forbidden(Exception):  # noqa: N818 - the HTTP name; rendered as 403 FORBIDDEN
    """Raised by ``assert_can`` and ``requires``; rendered as 403 ``{code, permission}``."""

    def __init__(self, permission: str | None) -> None:
        super().__init__(f"forbidden: {permission}")
        self.permission = permission


class _ProviderFailedError(Exception):
    pass


_GrantKey = tuple["PolicyService", UUID, UUID | None, str]
_memo: ContextVar[tuple[RequestContext, dict[_GrantKey, tuple[Grant, ...]]] | None] = ContextVar(
    "aip_access_grant_memo", default=None
)


def _request_memo() -> dict[_GrantKey, tuple[Grant, ...]] | None:
    """This request's grant memo, or ``None`` outside a request context (no memoising)."""
    try:
        ctx = get_context()
    except ContextMissingError:
        return None
    current = _memo.get()
    if current is not None and current[0] is ctx:
        return current[1]
    memo: dict[_GrantKey, tuple[Grant, ...]] = {}
    _memo.set((ctx, memo))
    return memo


def _matches(grant: Grant, action: str, resource: Resource | None) -> bool:
    if grant.permission != action:
        return False
    scope = grant.scope
    if isinstance(scope, TenantScope):
        return True
    if isinstance(scope, ProjectScope):  # pyright: ignore[reportUnnecessaryIsInstance]
        if resource is None or resource.project_id is None:
            return False
        return str(scope.project_id) == str(resource.project_id)
    return False  # an unknown scope type never matches (fail closed)


class PolicyService:
    def __init__(self, catalogue: Catalogue, providers: Iterable[GrantProvider] = ()) -> None:
        self.catalogue = catalogue
        self._providers: list[GrantProvider] = list(providers)

    def register(self, provider: GrantProvider) -> None:
        self._providers.append(provider)

    async def _grants(self, principal: AccessPrincipal) -> tuple[Grant, ...]:
        memo = _request_memo()
        key: _GrantKey = (self, principal.tenant_id, principal.actor_id, principal.kind)
        if memo is not None and key in memo:
            return memo[key]
        grants: list[Grant] = []
        for provider in self._providers:
            try:
                grants.extend(await provider.grants(principal))
            except Exception as exc:
                logger.exception("grant provider %s failed", type(provider).__name__)
                raise _ProviderFailedError from exc
        result = tuple(grants)
        if memo is not None:
            memo[key] = result
        return result

    async def can(
        self, principal: AccessPrincipal, action: str, resource: Resource | None = None
    ) -> Decision:
        if action not in self.catalogue:
            logger.warning("access check for unknown permission %r denied", action)
            return Decision(False, "unknown_permission")
        if not principal.active:
            return Decision(False, "inactive_principal")
        if resource is not None and resource.tenant_id not in (None, principal.tenant_id):
            return Decision(False, "no_grant")
        if principal.kind == "api_client":
            if action in principal.scopes:
                return Decision(True, "granted")
            return Decision(False, "no_grant")
        try:
            grants = await self._grants(principal)
        except _ProviderFailedError:
            return Decision(False, "provider_error")
        for grant in grants:
            if _matches(grant, action, resource):
                return Decision(True, "granted", grant)
        return Decision(False, "no_grant")

    async def assert_can(
        self, principal: AccessPrincipal, action: str, resource: Resource | None = None
    ) -> None:
        """Raise ``Forbidden(action)`` unless ``can`` allows it."""
        if not (await self.can(principal, action, resource)).allowed:
            raise Forbidden(action)

    async def filter_allowed[T](
        self,
        principal: AccessPrincipal,
        action: str,
        items: Iterable[T],
        resource_of: Callable[[T], Resource | None] | Callable[[T], Awaitable[Resource | None]],
    ) -> list[T]:
        """The items ``principal`` may ``action``, in their original order."""
        allowed: list[T] = []
        for item in items:
            resource = resource_of(item)
            if isinstance(resource, Awaitable):
                resource = await resource
            if (await self.can(principal, action, resource)).allowed:
                allowed.append(item)
        return allowed

    async def allowed_permissions(
        self, principal: AccessPrincipal, resource: Resource | None = None
    ) -> list[str]:
        """Every catalogue code ``principal`` holds for ``resource``, sorted (the abilities).

        Same rules as ``can``, but the grants are fetched once for the whole catalogue. A
        provider error yields no abilities (fail closed).
        """
        if not principal.active:
            return []
        if resource is not None and resource.tenant_id not in (None, principal.tenant_id):
            return []
        if principal.kind == "api_client":
            return [code for code in self.catalogue if code in principal.scopes]
        try:
            grants = await self._grants(principal)
        except _ProviderFailedError:
            return []
        return [
            code
            for code in self.catalogue
            if any(_matches(grant, code, resource) for grant in grants)
        ]
