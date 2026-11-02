"""ITP steps and their sign-offs (INSPECTIONS-03, ADR 0010, ADR 0035 §3 to §5).

An ITP-kind inspection has ordered steps (hold, witness, review and surveillance points). The step
machine is ``itp_rules``; this file loads, locks, checks and writes. Every call runs in the
caller's ``with_tenant`` transaction and locks the ITP row before the step (``FOR UPDATE``, in
that order), so sign-offs on one ITP are serialised and its hash chain has one tip.

- ``create_steps`` (``itp.manage``) sets up steps while the ITP is ``draft``, ``assignable`` or
  ``assigned`` (409 ``ITP_LOCKED`` later; 422 ``NOT_AN_ITP`` for other kinds; 409
  ``DUPLICATE_SEQ``).
- ``act`` takes ``ready`` (``itp.manage``), ``start`` or ``reopen`` (``itp.sign``); ``start``
  needs the ITP ``in_progress`` (409 ``ITP_NOT_IN_PROGRESS``).
- ``sign`` (``itp.sign``; ``itp.waive`` to waive) appends one ``inspection_signoffs`` row. A
  critical decision asks identity's ``check_signoff_assurance`` exactly as approvals does:
  ``step_up_required`` is 401 ``STEP_UP_REQUIRED`` and writes nothing; ``countersign_required``
  appends a ``pending_countersign`` row and leaves the step as it was (202); ``allow`` appends an
  ``applied`` row and moves the step. While a sign-off waits, only its decision is accepted
  (409 ``COUNTERSIGN_PENDING``), never from its signer (409 ``SELF_COUNTERSIGN``), and the
  countersigner must get ``allow`` (else 401 step-up or 403 ``COUNTERSIGN_ASSURANCE_REQUIRED``).
  A release or waiver sets ``released_at`` and emits ``itp_step.released`` v1.
- ``place_hold``/``clear_hold`` take no policy: issues has authorised its NCR. Each change emits
  ``itp_step.hold_changed`` v1.

A stale ``expectedSyncVersion`` is 409 with the current step (``ConflictError``). Another tenant's
step or ITP is 404 before any permission check.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.api import Actor
from aip.modules.identity.api import (
    Assurance,
    SignoffContext,
    StepUpRequiredError,
    check_signoff_assurance,
    derive_assurance,
    mfa_enrolled_at,
)
from aip.modules.inspections import repository as repo
from aip.modules.inspections.events import ITP_STEP_HOLD_CHANGED, ITP_STEP_RELEASED
from aip.modules.inspections.itp_rules import (
    DECISIONS,
    DONE_STATUSES,
    STEP_SETUP_STATES,
    Moved,
    Refused,
    Step,
    apply_action,
    apply_decision,
)
from aip.modules.inspections.policies import (
    ITP_MANAGE_PERMISSION,
    ITP_SIGN_PERMISSION,
    ITP_WAIVE_PERMISSION,
    VIEW_PERMISSION,
)
from aip.modules.inspections.responses import current_responses
from aip.modules.inspections.schemas import (
    ItpStepIn,
    ItpStepOut,
    ItpStepView,
    SignoffEntry,
    SignoffList,
)
from aip.modules.inspections.service import current_state
from aip.modules.inspections.signoff_chain import (
    content_hash,
    entry_hash,
    genesis_hash,
    verify_chain,
)
from aip.modules.inspections.tables import itp_steps
from aip.platform.access import PolicyService, Resource
from aip.platform.context import new_request_id
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.errors import ConflictError, NotFoundError
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "MESSAGE_KEYS",
    "HoldMismatchError",
    "ItpService",
    "SignResult",
    "StepAlreadyHeldError",
    "StepAlreadyReleasedError",
    "clear_hold",
    "is_step_released",
    "place_hold",
    "step_facts",
]

# The error codes this file raises and the term key of each message (config/terms).
MESSAGE_KEYS: Final[dict[str, str]] = {
    "NOT_AN_ITP": "itp.error.not_an_itp",
    "ITP_LOCKED": "itp.error.itp_locked",
    "DUPLICATE_SEQ": "itp.error.duplicate_seq",
    "ITP_NOT_IN_PROGRESS": "itp.error.itp_not_in_progress",
    "INVALID_STEP_ACTION": "itp.error.invalid_step_action",
    "BLOCKED_BY_HOLD": "itp.error.blocked_by_hold",
    "STEP_ON_HOLD": "itp.error.step_on_hold",
    "NOTICE_NOT_ELAPSED": "itp.error.notice_not_elapsed",
    "COMMENT_REQUIRED": "itp.error.comment_required",
    "COUNTERSIGN_PENDING": "itp.error.countersign_pending",
    "SELF_COUNTERSIGN": "itp.error.self_countersign",
    "COUNTERSIGN_ASSURANCE_REQUIRED": "itp.error.countersign_assurance_required",
    "STEP_ALREADY_RELEASED": "itp.error.step_already_released",
    "STEP_ALREADY_HELD": "itp.error.step_already_held",
    "HOLD_MISMATCH": "itp.error.hold_mismatch",
}

# How the signer authenticated, in the data model's ``auth_strength`` vocabulary.
_AUTH_STRENGTH: Final = {
    "password": "password",
    "device_pin": "pin",
    "passkey": "mfa",
    "totp": "mfa",
    "idp_mfa": "mfa",
}
_RECORD: Final = "itp_step"  # the outbox aggregate type of step events


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _error(status_code: int, code: str, **extra: Any) -> DomainError:
    return DomainError(status_code, code, messageKey=MESSAGE_KEYS[code], **extra)


class StepAlreadyReleasedError(DomainError):
    """An NCR hold was placed on a step that is already released or waived."""

    def __init__(self) -> None:
        super().__init__(
            409, "STEP_ALREADY_RELEASED", messageKey=MESSAGE_KEYS["STEP_ALREADY_RELEASED"]
        )


class StepAlreadyHeldError(DomainError):
    """Another issue already holds the step."""

    def __init__(self) -> None:
        super().__init__(409, "STEP_ALREADY_HELD", messageKey=MESSAGE_KEYS["STEP_ALREADY_HELD"])


class HoldMismatchError(DomainError):
    """The hold was cleared with an issue that does not hold the step."""

    def __init__(self) -> None:
        super().__init__(409, "HOLD_MISMATCH", messageKey=MESSAGE_KEYS["HOLD_MISMATCH"])


def _steps(rows: Sequence[Mapping[str, Any]]) -> list[Step]:
    return [Step.of(r) for r in rows]


def _refuse(outcome: Refused) -> DomainError:
    return _error(outcome.status_code, outcome.code)


async def step_facts(conn: AsyncConnection, row: Mapping[str, Any]) -> dict[str, int]:
    """The step guard facts of an inspection: open (not released or waived) and held steps."""
    if row["kind"] != "itp":
        return {"openStepCount": 0, "heldStepCount": 0}
    open_count, held_count = await repo.step_counts(conn, row["id"])
    return {"openStepCount": open_count, "heldStepCount": held_count}


async def is_step_released(conn: AsyncConnection, step_id: UUID) -> bool:
    """Released or waived and not held; false for a step not visible on ``conn``."""
    step = await repo.get_step(conn, step_id)
    return (
        step is not None and step["status"] in DONE_STATUSES and step["hold_flag_issue_id"] is None
    )


async def _emit_hold_changed(
    conn: AsyncConnection, step: Mapping[str, Any], issue_id: UUID, held: bool
) -> None:
    payload = {
        "stepId": str(step["id"]),
        "inspectionId": str(step["inspection_id"]),
        "issueId": str(issue_id),
        "held": held,
    }
    await emit(
        conn,
        ITP_STEP_HOLD_CHANGED,
        1,
        Aggregate(_RECORD, step["id"]),
        payload,
        asset_id=step["asset_id"],
    )


async def place_hold(conn: AsyncConnection, step_id: UUID, *, issue_id: UUID) -> ItpStepOut:
    """Put issue ``issue_id``'s NCR hold on the step; the same hold placed again changes nothing."""
    step = await repo.lock_step(conn, step_id)
    if step is None:
        raise NotFoundError(f"itp step {step_id} not found")
    if step["status"] in DONE_STATUSES:
        raise StepAlreadyReleasedError()
    holder = step["hold_flag_issue_id"]
    if holder == issue_id:
        return ItpStepOut.of(step)
    if holder is not None:
        raise StepAlreadyHeldError()
    row = await repo.set_hold(conn, step_id, issue_id)
    await _emit_hold_changed(conn, row, issue_id, held=True)
    return ItpStepOut.of(row)


async def clear_hold(conn: AsyncConnection, step_id: UUID, *, issue_id: UUID) -> ItpStepOut:
    """Lift issue ``issue_id``'s hold; a step without a hold is left as it is."""
    step = await repo.lock_step(conn, step_id)
    if step is None:
        raise NotFoundError(f"itp step {step_id} not found")
    holder = step["hold_flag_issue_id"]
    if holder is None:
        return ItpStepOut.of(step)
    if holder != issue_id:
        raise HoldMismatchError()
    row = await repo.set_hold(conn, step_id, None)
    await _emit_hold_changed(conn, row, issue_id, held=False)
    return ItpStepOut.of(row)


class SignResult:
    """A sign-off and the step after it; ``applied`` is false while it waits for a countersign."""

    __slots__ = ("applied", "signoff", "step")

    def __init__(self, step: ItpStepOut, signoff: SignoffEntry, *, applied: bool) -> None:
        self.step = step
        self.signoff = signoff
        self.applied = applied


class ItpService:
    """Stateless apart from the policy service; the connection carries the tenant."""

    def __init__(self, policy: PolicyService) -> None:
        self._policy = policy

    async def _assert(self, actor: Actor, permission: str, itp: Mapping[str, Any]) -> None:
        resource = Resource(project_id=itp["project_id"])
        await self._policy.assert_can(actor.principal, permission, resource)

    async def _can(self, actor: Actor, permission: str, itp: Mapping[str, Any]) -> bool:
        resource = Resource(project_id=itp["project_id"])
        return (await self._policy.can(actor.principal, permission, resource)).allowed

    async def _lock(
        self, conn: AsyncConnection, step_id: UUID
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """The step and its ITP, both locked (the ITP first); 404 when either is not visible."""
        found = await repo.get_step(conn, step_id)
        itp = None if found is None else await repo.lock_inspection(conn, found["inspection_id"])
        step = None if itp is None else await repo.lock_step(conn, step_id)
        if itp is None or step is None:
            raise NotFoundError(f"itp step {step_id} not found")
        return step, itp

    async def _load_viewable(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> dict[str, Any]:
        row = await repo.get_inspection(conn, inspection_id)
        if row is None:  # another tenant's (RLS) or an unknown id: 404 before any permission
            raise NotFoundError(f"inspection {inspection_id} not found")
        await self._assert(actor, VIEW_PERMISSION, row)
        return row

    async def create_steps(
        self,
        conn: AsyncConnection,
        actor: Actor,
        inspection_id: UUID,
        steps: Sequence[ItpStepIn],
    ) -> list[ItpStepView]:
        """Add steps to an ITP that has not started; returns every step of the ITP."""
        itp = await repo.lock_inspection(conn, inspection_id)
        if itp is None:
            raise NotFoundError(f"inspection {inspection_id} not found")
        await self._assert(actor, ITP_MANAGE_PERMISSION, itp)
        if itp["kind"] != "itp":
            raise _error(422, "NOT_AN_ITP")
        state = await current_state(conn, itp)
        if state not in STEP_SETUP_STATES:
            raise _error(409, "ITP_LOCKED", state=state)
        taken = {int(r["seq"]) for r in await repo.list_steps(conn, inspection_id)}
        repeated: list[int] = []
        for step in steps:
            if step.seq in taken:
                repeated.append(step.seq)
            taken.add(step.seq)
        if repeated:
            raise _error(409, "DUPLICATE_SEQ", seqs=sorted(set(repeated)))
        await repo.insert_steps(
            conn,
            [
                {
                    "id": _new_id(),
                    "tenant_id": actor.principal.tenant_id,
                    "inspection_id": itp["id"],
                    "asset_id": itp["asset_id"],
                    "seq": step.seq,
                    "title": step.title,
                    "point_type": step.point_type,
                    "acceptance_criteria": step.acceptance_criteria,
                    "task_id": step.task_id,
                    "blocks_task_id": step.blocks_task_id,
                    "notice_hours": step.notice_hours,
                }
                for step in steps
            ],
        )
        return await self._views(conn, actor, itp, state)

    async def list_steps(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> list[ItpStepView]:
        """The ITP's steps in ``seq`` order and what the caller may do now (``inspection.view``)."""
        itp = await self._load_viewable(conn, actor, inspection_id)
        return await self._views(conn, actor, itp, await current_state(conn, itp))

    async def _views(
        self, conn: AsyncConnection, actor: Actor, itp: Mapping[str, Any], state: str
    ) -> list[ItpStepView]:
        rows = await repo.list_steps(conn, itp["id"])
        pending = await repo.pending_steps(conn, itp["id"])
        may = {
            permission: await self._can(actor, permission, itp)
            for permission in (ITP_MANAGE_PERMISSION, ITP_SIGN_PERMISSION, ITP_WAIVE_PERMISSION)
        }
        steps = _steps(rows)
        now = datetime.now(UTC)
        views: list[ItpStepView] = []
        for row, step in zip(rows, steps, strict=True):
            waiting = pending.get(row["id"])
            available = [
                action
                for action, permission in (
                    ("ready", ITP_MANAGE_PERMISSION),
                    ("start", ITP_SIGN_PERMISSION),
                    ("reopen", ITP_SIGN_PERMISSION),
                )
                if may[permission]
                and (action != "start" or state == "in_progress")
                and isinstance(apply_action(step, action, steps), Moved)
                and waiting is None
            ]
            for decision in DECISIONS:
                permission = ITP_WAIVE_PERMISSION if decision == "waived" else ITP_SIGN_PERMISSION
                outcome = apply_decision(step, decision, comment="-", now=now, steps=steps)
                if not may[permission] or not isinstance(outcome, Moved):
                    continue
                if waiting is not None and (
                    waiting["decision"] != decision
                    or waiting["signer_user_id"] == actor.principal.actor_id
                ):
                    continue
                available.append(decision)
            views.append(
                ItpStepView.model_validate(
                    {
                        **row,
                        "held": row["hold_flag_issue_id"] is not None,
                        "available_actions": available,
                        "pending_countersign": None if waiting is None else waiting["decision"],
                    }
                )
            )
        return views

    async def act(
        self,
        conn: AsyncConnection,
        actor: Actor,
        step_id: UUID,
        action: str,
        *,
        expected_sync_version: int | None = None,
    ) -> ItpStepOut:
        """``ready``, ``start`` or ``reopen`` the step."""
        step, itp = await self._lock(conn, step_id)
        permission = ITP_MANAGE_PERMISSION if action == "ready" else ITP_SIGN_PERMISSION
        await self._assert(actor, permission, itp)
        if expected_sync_version is not None and expected_sync_version != step["sync_version"]:
            raise ConflictError(step)
        if action == "start" and await current_state(conn, itp) != "in_progress":
            raise _error(409, "ITP_NOT_IN_PROGRESS")
        steps = _steps(await repo.list_steps(conn, itp["id"]))
        outcome = apply_action(Step.of(step), action, steps)
        if isinstance(outcome, Refused):
            raise _refuse(outcome)
        patch: dict[str, Any] = {"status": outcome.to_status}
        if action == "ready":
            patch["ready_at"] = await repo.clock_timestamp(conn)
        row = await update_with_version(conn, itp_steps, step_id, step["sync_version"], patch)
        return ItpStepOut.of(row)

    async def sign(
        self,
        conn: AsyncConnection,
        actor: Actor,
        step_id: UUID,
        decision: str,
        signatory_role: str,
        *,
        comment: str | None = None,
        expected_sync_version: int | None = None,
    ) -> SignResult:
        """Record ``decision`` on the step; see the module docstring for every refusal."""
        step, itp = await self._lock(conn, step_id)
        permission = ITP_WAIVE_PERMISSION if decision == "waived" else ITP_SIGN_PERMISSION
        await self._assert(actor, permission, itp)
        signer = actor.principal.actor_id
        if signer is None:  # a sign-off always names a person
            raise DomainError(403, "FORBIDDEN")
        if expected_sync_version is not None and expected_sync_version != step["sync_version"]:
            raise ConflictError(step)
        last = await repo.last_step_signoff(conn, step_id)
        pending = last if last is not None and last["status"] == "pending_countersign" else None
        if pending is not None:
            if pending["decision"] != decision:
                raise _error(409, "COUNTERSIGN_PENDING")
            if pending["signer_user_id"] == signer:
                raise _error(409, "SELF_COUNTERSIGN")
        now = datetime.now(UTC)
        steps = _steps(await repo.list_steps(conn, itp["id"]))
        outcome = apply_decision(Step.of(step), decision, comment=comment, now=now, steps=steps)
        if isinstance(outcome, Refused):
            raise _refuse(outcome)
        assurance, status = await self._assurance(conn, actor, outcome, pending, now)

        signoff = await self._append(
            conn,
            actor,
            itp,
            step,
            decision=decision,
            signatory_role=signatory_role,
            action_code=str(outcome.action_code),
            comment=comment,
            assurance=assurance,
            status=status,
            countersigns_id=None if pending is None else pending["id"],
            now=now,
        )
        if status != "applied":  # waits for a countersign: the step stays, its version moves
            row = await update_with_version(conn, itp_steps, step_id, step["sync_version"], {})
            return SignResult(ItpStepOut.of(row), signoff, applied=False)
        patch: dict[str, Any] = {"status": outcome.to_status}
        if outcome.to_status in DONE_STATUSES:
            patch["released_at"] = now
        row = await update_with_version(conn, itp_steps, step_id, step["sync_version"], patch)
        if outcome.to_status in DONE_STATUSES:
            await self._emit_released(conn, itp, row, decision)
        return SignResult(ItpStepOut.of(row), signoff, applied=True)

    async def _assurance(
        self,
        conn: AsyncConnection,
        actor: Actor,
        outcome: Moved,
        pending: Mapping[str, Any] | None,
        now: datetime,
    ) -> tuple[Assurance, str]:
        """The signer's assurance and the sign-off's status; raises when it may not proceed."""
        if not outcome.critical:
            return derive_assurance(actor.session), "applied"
        actor_id = actor.principal.actor_id
        enrolled = actor_id is not None and await mfa_enrolled_at(conn, actor_id) is not None
        ctx = SignoffContext(
            session=actor.session, aal2_available=actor.session.aal >= 2 or enrolled, now=now
        )
        checked = await check_signoff_assurance(conn, ctx, str(outcome.action_code))
        if checked.decision == "step_up_required":
            raise StepUpRequiredError(actor.return_to)
        if checked.decision == "countersign_required":
            if pending is not None:
                raise _error(403, "COUNTERSIGN_ASSURANCE_REQUIRED")
            return checked.assurance, "pending_countersign"
        return checked.assurance, "applied"

    async def _append(
        self,
        conn: AsyncConnection,
        actor: Actor,
        itp: Mapping[str, Any],
        step: Mapping[str, Any],
        *,
        decision: str,
        signatory_role: str,
        action_code: str,
        comment: str | None,
        assurance: Assurance,
        status: str,
        countersigns_id: UUID | None,
        now: datetime,
    ) -> SignoffEntry:
        """Append the hash-chained sign-off (``seq = last + 1`` on this inspection)."""
        answers = (await current_responses(conn, itp)).answers
        last = await repo.last_signoff(conn, itp["id"])
        entry: dict[str, Any] = {
            "id": _new_id(),
            "tenant_id": actor.principal.tenant_id,
            "inspection_id": itp["id"],
            "itp_step_id": step["id"],
            "asset_id": itp["asset_id"],
            "seq": 1 if last is None else int(last["seq"]) + 1,
            "signatory_role": signatory_role,
            "signer_user_id": actor.principal.actor_id,
            "decision": decision,
            "action_code": action_code,
            "status": status,
            "countersigns_id": countersigns_id,
            "auth_strength": _AUTH_STRENGTH[assurance.method],
            "assurance_level": assurance.level,
            "assurance_method": assurance.method,
            "authenticated_at": assurance.authenticated_at,
            "device_id": assurance.device_id,
            "eligibility_result": None,  # INSPECTIONS-07
            "content_hash": content_hash(
                itp["id"],
                itp["template_revision_id"],
                step["id"],
                {key: answer.value for key, answer in answers.items()},
            ),
            "prev_hash": genesis_hash(itp["id"]) if last is None else str(last["entry_hash"]),
            "comment": comment,
            "signed_at": now,
        }
        entry["entry_hash"] = entry_hash(entry)
        return SignoffEntry.model_validate(await repo.insert_signoff(conn, entry))

    async def _emit_released(
        self,
        conn: AsyncConnection,
        itp: Mapping[str, Any],
        step: Mapping[str, Any],
        decision: str,
    ) -> None:
        project_id = itp["project_id"]
        task_id = step["task_id"]
        blocks_task_id = step["blocks_task_id"]
        payload = {
            "stepId": str(step["id"]),
            "inspectionId": str(itp["id"]),
            "assetId": str(step["asset_id"]),
            "projectId": None if project_id is None else str(project_id),
            "pointType": step["point_type"],
            "decision": decision,
            "taskId": None if task_id is None else str(task_id),
            "blocksTaskId": None if blocks_task_id is None else str(blocks_task_id),
            "releasedAt": step["released_at"].isoformat(),
        }
        await emit(
            conn,
            ITP_STEP_RELEASED,
            1,
            Aggregate(_RECORD, step["id"]),
            payload,
            asset_id=step["asset_id"],
        )

    async def signoffs(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> SignoffList:
        """Every sign-off of the inspection and whether the chain holds (``inspection.view``)."""
        await self._load_viewable(conn, actor, inspection_id)
        rows = await repo.list_signoffs(conn, inspection_id)
        chain = verify_chain(rows)
        return SignoffList(
            entries=[SignoffEntry.model_validate(r) for r in rows],
            chain_valid=chain.ok,
            broken_at_seq=getattr(chain, "broken_at_seq", None),
        )
