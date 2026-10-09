"""Just-in-time provisioning at the end of a Keycloak sign-in (IDENTITY-02, ADR 0005).

``JitLoginHandler`` is the ``ExternalLoginHandler`` (``api.py``) that replaces IDENTITY-01's
placeholder. It runs ``JitProvisioner.provision`` on the ``VerifiedExternalIdentity`` and then
hands the result to ``on_success`` (IDENTITY-03 issues the session there).

**Which tenant.** Never from anything the browser sends:

- SSO login (``idp_alias`` set): the tenant the email domain resolved to before sign-in (sealed in
  the pre-auth cookie) and that IDENTITY-01 checked against the ID token's ``identity_provider``.
  On top, the *token's* email domain must be claimed by that same tenant and IdP in
  ``login_directory`` (``domain_claimed``), so one tenant's IdP cannot assert another tenant's
  people.
- Local Keycloak account (``idp_alias`` NULL): the tenant the email is registered to
  (``identity_register_email``, local accounts only exist through invites). No registration is
  ``NOT_INVITED``; a registration for another tenant than the one the typed email's domain
  resolved to is ``TENANT_MISMATCH``.

**What happens** (``decide_jit``, a pure function), inside ``with_tenant(tenant)``:

1. the tenant must exist and be ``active`` (else ``TENANT_*``, as in ``require_active_tenant``);
2. per-identity advisory locks serialise concurrent first logins of the same person;
3. (a) a user linked to this Keycloak ``sub`` is refreshed (email, ``last_login_at``; ``invited``
   becomes ``active``); (b) else, with a verified email, a user with that email is linked (an
   invited user or an SSO user; a local account is never linked to an SSO identity:
   ``ACCOUNT_LINK_REQUIRED``); (c) else an SSO login creates a ``staff`` user plus a ``member``
   membership, and a local login is ``NOT_INVITED``;
4. refusals: ``USER_DEACTIVATED`` (login never reactivates), ``USER_REMOVED`` (soft-deleted),
   ``EMAIL_NOT_VERIFIED``, ``DOMAIN_NOT_CLAIMED``, ``SSO_REQUIRED``, ``MEMBERSHIP_INACTIVE``;
5. ``auth_event`` ``login.succeeded`` or ``login.denied`` (with the reason) in the same tenant.

Error bodies are ``{code, detail}`` and never name a tenant, an email or a token.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.responses import JSONResponse, Response

from aip.modules.identity import repository as repo
from aip.modules.identity.oidc import domain_of
from aip.modules.identity.repository import UserRow
from aip.modules.identity.schemas import VerifiedExternalIdentity
from aip.modules.tenancy.api import access_for_status, load_tenant
from aip.platform.db.session import before_tenant, with_tenant

__all__ = [
    "Denied",
    "JitDecision",
    "JitLoginHandler",
    "JitProvisioner",
    "Provisioned",
    "decide_jit",
]

logger = logging.getLogger(__name__)

DecisionKind = Literal["refresh", "link", "create", "refuse"]


@dataclass(frozen=True)
class JitDecision:
    kind: DecisionKind
    reason: str | None = None

    def __str__(self) -> str:
        return f"refuse:{self.reason}" if self.kind == "refuse" else self.kind

    @classmethod
    def refuse(cls, reason: str) -> JitDecision:
        return cls("refuse", reason)


REFRESH = JitDecision("refresh")
LINK = JitDecision("link")
CREATE = JitDecision("create")


def decide_jit(
    existing: UserRow | None,
    email_verified: bool,
    domain_claimed: bool,
    via_sso: bool,
    *,
    matched_by_subject: bool = False,
) -> JitDecision:
    """What to do with a verified sign-in. Pure; the order of the checks is the policy.

    ``existing`` is the user linked to the Keycloak subject (``matched_by_subject=True``), else
    the user with the token's email (live, or the latest soft-deleted one), else ``None``.
    ``domain_claimed`` only matters for SSO: the token email's domain belongs to this tenant's IdP.
    """
    if via_sso and not domain_claimed:
        return JitDecision.refuse("DOMAIN_NOT_CLAIMED")
    if existing is not None:
        if existing.deleted:
            return JitDecision.refuse("USER_REMOVED")
        if existing.status == "deactivated":
            return JitDecision.refuse("USER_DEACTIVATED")
    if existing is not None and matched_by_subject:
        if via_sso and not existing.sso_managed:
            return JitDecision.refuse("ACCOUNT_LINK_REQUIRED")
        if not via_sso and existing.sso_managed:
            return JitDecision.refuse("SSO_REQUIRED")
        return REFRESH
    if not email_verified:
        return JitDecision.refuse("EMAIL_NOT_VERIFIED")
    if existing is None:
        return CREATE if via_sso else JitDecision.refuse("NOT_INVITED")
    if existing.keycloak_user_id is not None:
        # The email already belongs to another Keycloak account: never re-link silently.
        return JitDecision.refuse("ACCOUNT_LINK_REQUIRED")
    if via_sso:
        return LINK if existing.sso_managed else JitDecision.refuse("ACCOUNT_LINK_REQUIRED")
    if existing.sso_managed:
        return JitDecision.refuse("SSO_REQUIRED")
    if existing.status == "invited":
        return LINK
    return JitDecision.refuse("ACCOUNT_LINK_REQUIRED")


# --- outcomes ----------------------------------------------------------------------------------

_MESSAGES: dict[str, str] = {
    "NOT_INVITED": "this account has not been invited",
    "ACCOUNT_LINK_REQUIRED": "this sign-in cannot be linked to the existing account automatically",
    "EMAIL_NOT_VERIFIED": "the email address of this account is not verified",
    "USER_DEACTIVATED": "this account is deactivated",
    "USER_REMOVED": "this account has been removed",
    "DOMAIN_NOT_CLAIMED": "this email domain is not registered for the identity provider",
    "SSO_REQUIRED": "this account must sign in with company SSO",
    "MEMBERSHIP_INACTIVE": "this account has no current membership",
    "TENANT_MISMATCH": "this account belongs to a different organisation sign-in",
    "TENANT_UNKNOWN": "sign-in is not available for this account",
    "TENANT_UNRESOLVED": "sign-in is not available for this account",
    "INVALID_SUBJECT": "the identity provider returned an unusable account id",
    "INVALID_EMAIL": "the identity provider returned an unusable email address",
}


@dataclass(frozen=True)
class Provisioned:
    tenant_id: UUID
    user_id: UUID
    action: Literal["created", "linked", "refreshed"]


@dataclass(frozen=True)
class Denied:
    code: str
    message: str
    status_code: int = 403


def _deny(code: str) -> Denied:
    return Denied(code=code, message=_MESSAGES.get(code, "sign-in was refused"))


TenantConnect = Callable[[UUID], AbstractAsyncContextManager[AsyncConnection]]
PreTenantConnect = Callable[[], AbstractAsyncContextManager[AsyncConnection]]


def _lock_key(tenant_id: UUID, kind: str, value: str) -> int:
    digest = hashlib.sha256(f"identity.jit\x00{tenant_id}\x00{kind}\x00{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _display_name(email: str) -> str:
    local = email.split("@", 1)[0].strip()
    return (local or email)[:200]


def _subject(raw: str) -> UUID | None:
    try:
        value = UUID(raw)
    except ValueError:
        return None
    return None if value.int == 0 else value


@dataclass(frozen=True)
class _Binding:
    tenant_id: UUID
    domain_claimed: bool


class JitProvisioner:
    """Applies ``decide_jit`` to the database (``connect``/``connect_pre`` injectable for tests)."""

    def __init__(
        self,
        connect: TenantConnect = with_tenant,
        connect_pre: PreTenantConnect = before_tenant,
    ) -> None:
        self._connect = connect
        self._connect_pre = connect_pre

    async def _binding(
        self, identity: VerifiedExternalIdentity, email: str, domain: str
    ) -> _Binding | Denied:
        """The tenant this identity belongs to, from server-side data only."""
        async with self._connect_pre() as conn:
            if identity.idp_alias is not None:
                if identity.tenant_id is None:
                    return _deny("TENANT_UNRESOLVED")
                target = await repo.resolve_login(conn, "email_domain", domain)
                claimed = (
                    target is not None
                    and target.tenant_id == identity.tenant_id
                    and target.idp_alias == identity.idp_alias
                )
                return _Binding(identity.tenant_id, claimed)
            registered = await repo.resolve_login(conn, "email", email)
        if registered is None:
            return _deny("NOT_INVITED")
        if identity.tenant_id is not None and identity.tenant_id != registered.tenant_id:
            return _deny("TENANT_MISMATCH")
        return _Binding(registered.tenant_id, True)

    async def provision(self, identity: VerifiedExternalIdentity) -> Provisioned | Denied:
        via_sso = identity.idp_alias is not None
        subject = _subject(identity.subject)
        if subject is None:
            logger.info("jit refused: INVALID_SUBJECT")
            return _deny("INVALID_SUBJECT")
        email = identity.email.strip()
        try:
            domain = domain_of(email)
        except ValueError:
            logger.info("jit refused: INVALID_EMAIL")
            return _deny("INVALID_EMAIL")
        binding = await self._binding(identity, email, domain)
        if isinstance(binding, Denied):
            logger.info("jit refused before tenant: %s", binding.code)
            return binding
        for attempt in (1, 2):
            try:
                async with self._connect(binding.tenant_id) as conn:
                    return await self._apply(conn, identity, binding, subject, email, via_sso)
            except IntegrityError:
                # A concurrent first login committed between our read and write despite the
                # locks (e.g. a different subject with the same email); re-read once.
                if attempt == 2:
                    raise
                logger.info("jit retry after a concurrent write")
        raise AssertionError("unreachable")  # pragma: no cover

    async def _apply(
        self,
        conn: AsyncConnection,
        identity: VerifiedExternalIdentity,
        binding: _Binding,
        subject: UUID,
        email: str,
        via_sso: bool,
    ) -> Provisioned | Denied:
        tenant_id = binding.tenant_id
        method = "sso" if via_sso else "local"
        base_detail: dict[str, object] = {"method": method, "subject": str(subject)}
        if identity.idp_alias is not None:
            base_detail["idpAlias"] = identity.idp_alias

        async def denied(code: str, user_id: UUID | None = None) -> Denied:
            await repo.record_auth_event(
                conn,
                tenant_id=tenant_id,
                event_type="login.denied",
                user_id=user_id,
                detail={**base_detail, "reason": code.lower()},
            )
            logger.info("jit refused: %s", code)
            return _deny(code)

        tenant = await load_tenant(conn, tenant_id)
        if tenant is None or tenant.id != tenant_id:
            logger.info("jit refused: TENANT_UNKNOWN")
            return _deny("TENANT_UNKNOWN")  # no tenant row to attach an event to
        tenant_denial = access_for_status(tenant.status)
        if tenant_denial is not None:
            await denied(tenant_denial.code)
            return Denied(tenant_denial.code, tenant_denial.message, tenant_denial.status_code)

        # Serialise concurrent sign-ins of the same person (same subject or same email) within the
        # tenant; always in the same order, so two keys never deadlock.
        for key in sorted(
            (
                _lock_key(tenant_id, "sub", str(subject)),
                _lock_key(tenant_id, "email", email.lower()),
            )
        ):
            await repo.advisory_xact_lock(conn, key)

        existing = await repo.find_by_keycloak_user_id(conn, subject)
        matched_by_subject = existing is not None
        if existing is None:
            existing = await repo.find_by_email(conn, email)
            if existing is None:
                existing = await repo.find_deleted_by_email(conn, email)

        decision = decide_jit(
            existing,
            identity.email_verified,
            binding.domain_claimed,
            via_sso,
            matched_by_subject=matched_by_subject,
        )
        if decision.kind == "refuse":
            assert decision.reason is not None
            return await denied(decision.reason, existing.id if existing is not None else None)

        if decision.kind == "create":
            user_id = await repo.insert_user(
                conn,
                tenant_id=tenant_id,
                email=email,
                display_name=_display_name(email),
                user_class="staff",
                status="active",
                sso_managed=True,
                idp_alias=identity.idp_alias,
                keycloak_user_id=subject,
                last_login_at=func.now(),
            )
            await repo.insert_membership(
                conn, tenant_id=tenant_id, user_id=user_id, membership_type="member"
            )
            action: Literal["created", "linked", "refreshed"] = "created"
        else:
            assert existing is not None
            user_id = existing.id
            if not await repo.has_current_membership(conn, user_id):
                return await denied("MEMBERSHIP_INACTIVE", user_id)
            values: dict[str, object] = {"last_login_at": func.now()}
            if existing.status == "invited":
                values["status"] = "active"
            if via_sso:
                values["idp_alias"] = identity.idp_alias
            if decision.kind == "link":
                values["keycloak_user_id"] = subject
                action = "linked"
            else:
                action = "refreshed"
                if (
                    identity.email_verified
                    and email.lower() != existing.email.lower()
                    and await self._email_free(conn, email, existing)
                ):
                    values["email"] = email
            await repo.update_user(conn, user_id, **values)

        await repo.record_auth_event(
            conn,
            tenant_id=tenant_id,
            event_type="login.succeeded",
            user_id=user_id,
            detail={**base_detail, "action": action},
        )
        return Provisioned(tenant_id=tenant_id, user_id=user_id, action=action)

    async def _email_free(self, conn: AsyncConnection, email: str, user: UserRow) -> bool:
        """A linked user may take a new email only when no other live user in the tenant has it.

        For a local account the new email already resolved to this tenant (the binding), so the
        registration stays consistent; an SSO email was checked against the claimed domains.
        """
        other = await repo.find_by_email(conn, email)
        return other is None or other.id == user.id


OnSuccess = Callable[[VerifiedExternalIdentity, Provisioned], Awaitable[Response]]


async def default_on_success(identity: VerifiedExternalIdentity, result: Provisioned) -> Response:
    """Until IDENTITY-03 issues sessions: ``AIP_ENV=test`` returns the user id; elsewhere 501."""
    if os.environ.get("AIP_ENV", "") == "test":
        return JSONResponse({"userId": str(result.user_id), "action": result.action})
    return JSONResponse(
        {"code": "SESSION_NOT_IMPLEMENTED", "detail": "sign-in sessions are not built yet"},
        status_code=501,
    )


class JitLoginHandler:
    """``ExternalLoginHandler``: provision, then ``on_success``; a refusal is ``{code, detail}``."""

    def __init__(
        self, provisioner: JitProvisioner | None = None, on_success: OnSuccess | None = None
    ) -> None:
        self._provisioner = provisioner or JitProvisioner()
        self._on_success = on_success or default_on_success

    async def __call__(self, identity: VerifiedExternalIdentity) -> Response:
        result = await self._provisioner.provision(identity)
        if isinstance(result, Denied):
            return JSONResponse(
                {"code": result.code, "detail": result.message}, status_code=result.status_code
            )
        return await self._on_success(identity, result)
