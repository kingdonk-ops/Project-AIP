"""Section and report acknowledgements (INSPECTIONS-10, ADR 0041 §3-§6).

The person doing an inspection ticks each visible section "complete" and then the whole report.
A tick validates the answers with the shared FORMS-02 evaluator and locks them; only the person
who ticked can untick, and every submit action is guarded on a current report tick
(``record.reportAcknowledged``). Every tick, untick and rework clearing is one append-only
``inspection_acknowledgements`` row; a scope's state is its latest row.

**The lock rule** (:func:`locked_scopes`): a scope is locked when its latest row is a ``tick`` made
after the inspection last entered ``rework_required``. Request Rework clears every tick, and it
writes a ``cleared_by_rework`` row for each one (:func:`clear_for_rework`): in the transition's
transaction when it goes through ``/api/v1/inspections``, else when ``sync_state`` follows the
``workflow.transitioned`` event. Approvals has no in-transaction host hook, so until that event is
handled the time rule alone keeps rework unlocked.

Every ``AcknowledgementService`` call runs in the caller's ``with_tenant`` transaction and locks the
inspection row ``FOR UPDATE`` and then its workflow instance (``lock_lifecycle``), so it serialises
with answer writes and with transitions from either route: a submit through ``/api/v1/approvals``
waits and its guard sees the committed ticks. Any 4xx writes nothing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.api import Actor, ApprovalsApi
from aip.modules.forms.api import AnswerEvaluation, FormsApi, evaluate_answers
from aip.modules.inspections import repository as repo
from aip.modules.inspections.events import (
    INSPECTION_REPORT_ACKNOWLEDGED,
    INSPECTION_SECTION_ACKNOWLEDGED,
)
from aip.modules.inspections.policies import (
    RECORD_TYPE,
    RESPOND_PERMISSION,
    RESPOND_STATES,
    REWORK_STATE,
    VIEW_PERMISSION,
)
from aip.modules.inspections.schemas import Acknowledgements, AcknowledgementState
from aip.modules.inspections.service import current_state, lock_lifecycle
from aip.platform.access import PolicyService, Resource
from aip.platform.context import new_request_id
from aip.platform.db.errors import NotFoundError
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "MESSAGE_KEYS",
    "REPORT",
    "AcknowledgementService",
    "Scope",
    "acknowledgement_facts",
    "acknowledgements_of",
    "assert_unlocked",
    "clear_for_rework",
    "current_locks",
    "locked_scopes",
]

# The error codes this file raises and the term key of each message (config/terms).
MESSAGE_KEYS: Final[dict[str, str]] = {
    "INSPECTION_NOT_EDITABLE": "inspection.error.not_editable",
    "UNKNOWN_SECTION": "inspection.error.unknown_section",
    "SECTION_NOT_VISIBLE": "inspection.error.section_not_visible",
    "SECTION_ALREADY_ACKNOWLEDGED": "inspection.error.section_already_acknowledged",
    "SECTION_INCOMPLETE": "inspection.error.section_incomplete",
    "NOT_ACKNOWLEDGER": "inspection.error.not_acknowledger",
    "REPORT_ACKNOWLEDGED": "inspection.error.report_acknowledged",
    "REPORT_ALREADY_ACKNOWLEDGED": "inspection.error.report_already_acknowledged",
    "SECTIONS_NOT_ACKNOWLEDGED": "inspection.error.sections_not_acknowledged",
    "REPORT_INCOMPLETE": "inspection.error.report_incomplete",
    "SECTION_LOCKED": "inspection.error.section_locked",
    "REPORT_LOCKED": "inspection.error.report_locked",
}

Scope = tuple[Literal["section", "report"], str | None]
REPORT: Final[Scope] = ("report", None)

_REQUIRED: Final = "REQUIRED"  # the evaluator's code for a required field with no answer
_approvals = ApprovalsApi()
_forms = FormsApi()


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _error(status_code: int, code: str, **extra: Any) -> DomainError:
    return DomainError(status_code, code, messageKey=MESSAGE_KEYS[code], **extra)


def _section(key: str) -> Scope:
    return ("section", key)


# --- the lock rule (pure) ----------------------------------------------------------------------


def locked_scopes(
    latest: Iterable[Mapping[str, Any]], cleared_before: datetime | None
) -> dict[Scope, Mapping[str, Any]]:
    """The locked scopes and the tick that locks each: the scope's latest row is a ``tick`` made
    after ``cleared_before`` (the last entry into ``rework_required``, ``None`` if never)."""
    return {
        (r["scope"], r["section_key"]): r
        for r in latest
        if r["action"] == "tick" and (cleared_before is None or r["acted_at"] > cleared_before)
    }


async def current_locks(
    conn: AsyncConnection, row: Mapping[str, Any]
) -> dict[Scope, Mapping[str, Any]]:
    """The inspection ``row``'s locked scopes now."""
    latest = await repo.current_acknowledgements(conn, row["id"])
    cleared_before = await _approvals.state_entered_at(
        conn, row["workflow_instance_id"], REWORK_STATE
    )
    return locked_scopes(latest, cleared_before)


async def acknowledgement_facts(conn: AsyncConnection, row: Mapping[str, Any]) -> dict[str, bool]:
    """The submit guard facts: which submit applies, and whether the report is ticked."""
    return {
        "hasSupervisorReview": bool(row["has_supervisor_review"]),
        "reportAcknowledged": REPORT in await current_locks(conn, row),
    }


def _state(lock: Mapping[str, Any] | None) -> AcknowledgementState:
    if lock is None:
        return AcknowledgementState(locked=False)
    return AcknowledgementState(locked=True, by=lock["actor"], at=lock["acted_at"])


async def _revision_schema(conn: AsyncConnection, row: Mapping[str, Any]) -> dict[str, Any]:
    revision = await _forms.get_revision(conn, row["template_revision_id"])
    if revision is None:  # a pinned revision is frozen and never deleted
        raise RuntimeError(f"inspection {row['id']}: pinned revision is not readable")
    return revision.schema


async def acknowledgements_of(conn: AsyncConnection, row: Mapping[str, Any]) -> Acknowledgements:
    """Every section of the pinned revision and the report, locked or not."""
    schema = await _revision_schema(conn, row)
    locks = await current_locks(conn, row)
    return Acknowledgements(
        sections={s["key"]: _state(locks.get(_section(s["key"]))) for s in schema["sections"]},
        report=_state(locks.get(REPORT)),
    )


async def assert_unlocked(
    conn: AsyncConnection, row: Mapping[str, Any], field_keys: Iterable[str]
) -> None:
    """409 when the report is ticked (``REPORT_LOCKED``) or a field is in a ticked section
    (``SECTION_LOCKED`` with its ``sectionKey``). For answer writes in the respond states."""
    locks = await current_locks(conn, row)
    if not locks:
        return
    if REPORT in locks:
        raise _error(409, "REPORT_LOCKED")
    schema = await _revision_schema(conn, row)
    section_of = {f["key"]: s["key"] for s in schema["sections"] for f in s["fields"]}
    for key in field_keys:
        section_key = section_of.get(key)  # an unknown field is refused later, as before
        if section_key is not None and _section(section_key) in locks:
            raise _error(409, "SECTION_LOCKED", sectionKey=section_key)


async def clear_for_rework(
    conn: AsyncConnection,
    row: Mapping[str, Any],
    actor_id: UUID,
    *,
    entered_at: datetime | None = None,
) -> int:
    """Write ``cleared_by_rework`` for every scope whose latest row is a ``tick`` (made no later
    than ``entered_at``, when given: a tick after the rework began stands). Idempotent; returns
    how many it cleared."""
    now = await repo.clock_timestamp(conn)
    cleared = 0
    for latest in await repo.current_acknowledgements(conn, row["id"]):
        if latest["action"] != "tick":
            continue
        if entered_at is not None and latest["acted_at"] > entered_at:
            continue
        await _insert(
            conn,
            row,
            latest["scope"],
            latest["section_key"],
            "cleared_by_rework",
            actor_id,
            now,
            tenant_id=latest["tenant_id"],
        )
        cleared += 1
    return cleared


async def _insert(
    conn: AsyncConnection,
    row: Mapping[str, Any],
    scope: str,
    section_key: str | None,
    action: str,
    actor_id: UUID,
    now: datetime,
    *,
    tenant_id: UUID,
) -> dict[str, Any]:
    return await repo.insert_acknowledgement(
        conn,
        {
            "id": _new_id(),
            "tenant_id": tenant_id,
            "inspection_id": row["id"],
            "scope": scope,
            "section_key": section_key,
            "action": action,
            "actor": actor_id,
            "revision_id": row["template_revision_id"],
            "acted_at": now,
            "created_at": now,
        },
    )


def _verdict(missing: list[str], invalid: list[str], rule_failures: list[str]) -> dict[str, Any]:
    return {"missingRequired": missing, "invalid": invalid, "ruleFailures": rule_failures}


def _report_verdict(evaluation: AnswerEvaluation) -> dict[str, Any]:
    missing = [e.field_key for e in evaluation.errors if e.code == _REQUIRED]
    invalid = [e.field_key for e in evaluation.errors if e.code != _REQUIRED]
    rules = [rule for s in evaluation.sections.values() for rule in s.rule_failures]
    return _verdict(missing, invalid, rules)


class AcknowledgementService:
    """Stateless apart from the policy service; the connection carries the tenant."""

    def __init__(self, policy: PolicyService) -> None:
        self._policy = policy

    async def _lock_editable(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> dict[str, Any]:
        """The inspection, locked; ``inspection.respond`` and a respond state, else 403/409."""
        row = await repo.lock_inspection(conn, inspection_id)
        if row is None:  # another tenant's (RLS) or an unknown id: 404 before any permission
            raise NotFoundError(f"inspection {inspection_id} not found")
        resource = Resource(project_id=row["project_id"])
        await self._policy.assert_can(actor.principal, RESPOND_PERMISSION, resource)
        await lock_lifecycle(conn, row)  # a submit from any route waits for this write
        state = await current_state(conn, row)
        if state not in RESPOND_STATES:  # from supervisor review on, nobody unticks anything
            raise _error(409, "INSPECTION_NOT_EDITABLE", state=state)
        return row

    async def _evaluate(
        self, conn: AsyncConnection, row: Mapping[str, Any]
    ) -> tuple[dict[str, Any], AnswerEvaluation]:
        schema = await _revision_schema(conn, row)
        current = await repo.current_responses(conn, row["id"])
        answers = {key: r["value"] for key, r in current.items()}
        return schema, evaluate_answers(schema, answers, mode="submit")

    async def _record(
        self,
        conn: AsyncConnection,
        actor: Actor,
        row: Mapping[str, Any],
        scope: Scope,
        action: str,
    ) -> Acknowledgements:
        now = await repo.clock_timestamp(conn)  # after the lock: later than any earlier row
        actor_id = actor.principal.actor_id
        if actor_id is None:  # a system principal never acknowledges
            raise RuntimeError("an acknowledgement needs a user")
        await _insert(
            conn,
            row,
            scope[0],
            scope[1],
            action,
            actor_id,
            now,
            tenant_id=actor.principal.tenant_id,
        )
        if action == "tick":
            await _emit_acknowledged(conn, row, scope, actor_id)
        return await acknowledgements_of(conn, row)

    async def tick_section(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID, section_key: str
    ) -> Acknowledgements:
        """Validate the section's current answers and lock them."""
        row = await self._lock_editable(conn, actor, inspection_id)
        schema, evaluation = await self._evaluate(conn, row)
        if section_key not in {s["key"] for s in schema["sections"]}:
            raise _error(422, "UNKNOWN_SECTION", sectionKey=section_key)
        result = evaluation.sections[section_key]
        if not result.visible:
            raise _error(422, "SECTION_NOT_VISIBLE", sectionKey=section_key)
        if _section(section_key) in await current_locks(conn, row):
            raise _error(409, "SECTION_ALREADY_ACKNOWLEDGED", sectionKey=section_key)
        if not result.complete:
            raise _error(
                422,
                "SECTION_INCOMPLETE",
                sectionKey=section_key,
                **_verdict(result.missing_required, result.invalid, result.rule_failures),
            )
        return await self._record(conn, actor, row, _section(section_key), "tick")

    async def untick_section(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID, section_key: str
    ) -> Acknowledgements:
        """Unlock a section the caller ticked, while the report is not ticked."""
        row = await self._lock_editable(conn, actor, inspection_id)
        schema = await _revision_schema(conn, row)
        if section_key not in {s["key"] for s in schema["sections"]}:
            raise _error(422, "UNKNOWN_SECTION", sectionKey=section_key)
        locks = await current_locks(conn, row)
        self._assert_acknowledger(actor, locks.get(_section(section_key)))
        if REPORT in locks:
            raise _error(409, "REPORT_ACKNOWLEDGED")
        return await self._record(conn, actor, row, _section(section_key), "untick")

    async def tick_report(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> Acknowledgements:
        """With every visible section ticked, check the whole form once more and lock it."""
        row = await self._lock_editable(conn, actor, inspection_id)
        locks = await current_locks(conn, row)
        if REPORT in locks:
            raise _error(409, "REPORT_ALREADY_ACKNOWLEDGED")
        _, evaluation = await self._evaluate(conn, row)
        open_sections = [
            key
            for key, result in evaluation.sections.items()
            if result.visible and _section(key) not in locks
        ]
        if open_sections:
            raise _error(422, "SECTIONS_NOT_ACKNOWLEDGED", sectionKeys=open_sections)
        if not evaluation.complete:
            raise _error(422, "REPORT_INCOMPLETE", **_report_verdict(evaluation))
        return await self._record(conn, actor, row, REPORT, "tick")

    async def untick_report(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> Acknowledgements:
        """Unlock the report the caller ticked (its sections stay ticked)."""
        row = await self._lock_editable(conn, actor, inspection_id)
        self._assert_acknowledger(actor, (await current_locks(conn, row)).get(REPORT))
        return await self._record(conn, actor, row, REPORT, "untick")

    @staticmethod
    def _assert_acknowledger(actor: Actor, lock: Mapping[str, Any] | None) -> None:
        """Only the person who ticked a scope may untick it (ADR 0041 §3: safe handover)."""
        if lock is None or lock["actor"] != actor.principal.actor_id:
            raise _error(403, "NOT_ACKNOWLEDGER")

    async def current(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> Acknowledgements:
        """What is locked now (``inspection.view``)."""
        row = await repo.get_inspection(conn, inspection_id)
        if row is None:
            raise NotFoundError(f"inspection {inspection_id} not found")
        resource = Resource(project_id=row["project_id"])
        await self._policy.assert_can(actor.principal, VIEW_PERMISSION, resource)
        return await acknowledgements_of(conn, row)


async def _emit_acknowledged(
    conn: AsyncConnection, row: Mapping[str, Any], scope: Scope, actor_id: UUID
) -> None:
    name = INSPECTION_REPORT_ACKNOWLEDGED if scope == REPORT else INSPECTION_SECTION_ACKNOWLEDGED
    payload = {
        "inspectionId": str(row["id"]),
        "scope": scope[0],
        "sectionKey": scope[1],
        "actor": str(actor_id),
    }
    await emit(conn, name, 1, Aggregate(RECORD_TYPE, row["id"]), payload, asset_id=row["asset_id"])
