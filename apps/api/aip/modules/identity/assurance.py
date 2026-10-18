"""Sign-off assurance: one decision for every critical action (IDENTITY-04 Part D, ADR 0010).

- ``derive_assurance(session)`` (pure): how the person proved who they are, as an ``Assurance``
  (level 1 or 2, method, when, device). Every decision carries it, so the caller stores it with
  the signature or decision record.
- ``check_signoff_assurance(conn, ctx, action_code)``: reads the tenant's ``signoff_policy`` row
  for the action (no row: min aal 2, 10 minutes) and returns a ``SignoffDecision``:

  - ``allow`` when the level meets the minimum and the authentication is fresh enough;
  - ``step_up_required`` (with the step-up URL) when the person has *any* aal2 method available
    (a Keycloak second factor, a registered device or an IdP that reports MFA);
  - ``countersign_required`` otherwise: the action is recorded but takes no effect until a
    supervisor with the required assurance countersigns.

ADR 0010 addendum (owner answers 2026-10-10), for a client's hold-point release: with the project
setting ``holdpoint_client_pin_only`` off, a PIN-only client signature is not enough
(``step_up_required``: the client's phone confirms) and an offline release is not allowed
(``countersign_required``); with it on, a PIN signature is ``allow``, or ``allow_provisional``
while offline (the server validates it on sync). The project setting itself lives with projects
(carried forward); callers pass its value in ``SignoffContext``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.identity import repository as repo

__all__ = [
    "DEFAULT_MAX_AGE_MIN",
    "DEFAULT_MIN_AAL",
    "HOLD_POINT_RELEASE",
    "SIGNOFF_ACTIONS",
    "Assurance",
    "AssuranceMethod",
    "SessionFacts",
    "SignoffContext",
    "SignoffDecision",
    "check_signoff_assurance",
    "derive_assurance",
    "effective_policy",
]

DEFAULT_MIN_AAL: Final = 2
DEFAULT_MAX_AGE_MIN: Final = 10
HOLD_POINT_RELEASE: Final = "hold_point.release"
# The critical actions ADR 0010 names; the workflow definition marks which transitions use them.
SIGNOFF_ACTIONS: Final = (HOLD_POINT_RELEASE, "witness.countersign", "itp.signoff", "record.seal")

AssuranceMethod = Literal["passkey", "device_pin", "totp", "idp_mfa", "password"]
DecisionKind = Literal["allow", "allow_provisional", "step_up_required", "countersign_required"]

_PASSKEY_AMR: Final = frozenset({"hwk", "webauthn", "swk", "fido"})
_IDP_MFA_AMR: Final = frozenset({"mfa", "otp", "hwk", "swk", "fido"})


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class Assurance(_Camel):
    """What the signer's authentication proves; stored on every signature and decision."""

    level: Literal[1, 2]
    method: AssuranceMethod
    authenticated_at: datetime | None
    device_id: UUID | None = None


class SignoffDecision(_Camel):
    decision: DecisionKind
    assurance: Assurance
    action_code: str
    min_aal: Literal[1, 2]
    max_age_min: int
    step_up_url: str | None = None


@dataclass(frozen=True)
class SessionFacts:
    """The parts of a session assurance looks at (from ``Principal`` or ``user_session``).

    A brokered session's ``amr`` holds ``fed`` plus the upstream IdP's values (IDENTITY-04); a
    field-device session (``audience='device'``) holds ``pin`` once the PIN was verified.
    """

    aal: int
    amr: Sequence[str]
    authenticated_at: datetime | None
    audience: str = "app"
    device_id: UUID | None = None


def derive_assurance(session: SessionFacts) -> Assurance:
    amr = set(session.amr)
    at = session.authenticated_at
    if session.audience == "device" and session.device_id is not None and "pin" in amr:
        return Assurance(
            level=2, method="device_pin", authenticated_at=at, device_id=session.device_id
        )
    if session.aal >= 2:
        if "fed" in amr and amr & _IDP_MFA_AMR:
            return Assurance(level=2, method="idp_mfa", authenticated_at=at)
        if amr & _PASSKEY_AMR:
            return Assurance(level=2, method="passkey", authenticated_at=at)
        if "fed" not in amr:
            # A local Keycloak account reaches aal2 only with a second factor: TOTP unless a key
            # was used (the enrolment sign-in lists only "pwd", the factor was just configured).
            return Assurance(level=2, method="totp", authenticated_at=at)
    return Assurance(level=1, method="password", authenticated_at=at)


@dataclass(frozen=True)
class SignoffContext:
    """Who is signing and how; built by the caller (APPROVALS-02) from the request.

    ``aal2_available``: the signer could reach aal2 right now (a Keycloak second factor or passkey
    enrolled, a registered device, or an IdP that reports MFA). ``client_signature``,
    ``holdpoint_client_pin_only`` and ``offline`` carry the ADR 0010 addendum's project setting.
    """

    session: SessionFacts
    aal2_available: bool
    now: datetime
    step_up_url: str | None = None
    client_signature: bool = False
    holdpoint_client_pin_only: bool = False
    offline: bool = False


async def effective_policy(conn: AsyncConnection, action_code: str) -> tuple[int, int]:
    """``(min_aal, max_age_min)`` for the bound tenant: its row, else ``(2, 10)``."""
    row = await repo.get_signoff_policy(conn, action_code)
    if row is None:
        return DEFAULT_MIN_AAL, DEFAULT_MAX_AGE_MIN
    return row.min_aal, row.step_up_max_age_min


def decide(
    ctx: SignoffContext, action_code: str, *, min_aal: int, max_age_min: int
) -> SignoffDecision:
    """The pure decision behind ``check_signoff_assurance``."""
    assurance = derive_assurance(ctx.session)
    minimum: Literal[1, 2] = 2 if min_aal >= 2 else 1

    def result(kind: DecisionKind) -> SignoffDecision:
        return SignoffDecision(
            decision=kind,
            assurance=assurance,
            action_code=action_code,
            min_aal=minimum,
            max_age_min=max_age_min,
            step_up_url=ctx.step_up_url if kind == "step_up_required" else None,
        )

    def fresh() -> bool:
        at = assurance.authenticated_at
        return at is not None and ctx.now - at <= timedelta(minutes=max_age_min)

    if action_code == HOLD_POINT_RELEASE and ctx.client_signature:
        if assurance.method == "device_pin":
            if not ctx.holdpoint_client_pin_only:
                return result("countersign_required" if ctx.offline else "step_up_required")
            return result("allow_provisional" if ctx.offline else "allow")
        if ctx.offline:
            return result("countersign_required")
    if assurance.level >= minimum and fresh():
        return result("allow")
    if ctx.aal2_available and not ctx.offline:
        return result("step_up_required")
    return result("countersign_required")


async def check_signoff_assurance(
    conn: AsyncConnection, ctx: SignoffContext, action_code: str
) -> SignoffDecision:
    """``allow`` / ``allow_provisional`` / ``step_up_required`` / ``countersign_required`` for
    ``action_code`` in the bound tenant (``conn`` from ``with_tenant``)."""
    min_aal, max_age_min = await effective_policy(conn, action_code)
    return decide(ctx, action_code, min_aal=min_aal, max_age_min=max_age_min)
