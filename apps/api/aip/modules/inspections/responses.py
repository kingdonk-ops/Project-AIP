"""Inspection answers (INSPECTIONS-02): append-only responses, the current view and validation.

Every answer is one ``inspection_responses`` row; a correction is a new row that supersedes the
field's current one, so nothing is ever updated or deleted. Answers are validated on the server
against the inspection's pinned form revision with the shared FORMS-02 evaluator
(``aip.modules.forms.api.evaluate_answers``, the one the web renderer mirrors); there is no second
copy of the rules here.

``ResponseService.submit`` runs in the caller's ``with_tenant`` transaction and locks the
inspection row first, so writes per inspection are serialised: the ``clientId`` check is then
exact (a partitioned table cannot carry a unique key, ADR 0031) and the ``clock_timestamp()`` taken
after the lock orders every answer after the one it supersedes. Any 4xx writes nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.api import Actor
from aip.modules.forms.api import AnswerEvaluation, FormsApi, evaluate_answers
from aip.modules.inspections import repository as repo
from aip.modules.inspections.events import INSPECTION_ANSWER_FAILED
from aip.modules.inspections.policies import (
    RECORD_TYPE,
    RESPOND_PERMISSION,
    REVIEW_EDIT_PERMISSION,
    VIEW_PERMISSION,
    emits_answer_failed,
    permissions_to_respond,
)
from aip.modules.inspections.schemas import (
    AnswerIn,
    AnswerOut,
    AnswersEvaluation,
    CurrentResponses,
    ResponseEntry,
    ResponseResult,
)
from aip.modules.inspections.service import current_state
from aip.platform.access import PolicyService, Resource
from aip.platform.context import new_request_id
from aip.platform.db.errors import NotFoundError
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "MESSAGE_KEYS",
    "ResponseService",
    "answer_facts",
    "current_responses",
]

# The error codes this file raises and the term key of each message (config/terms).
MESSAGE_KEYS: Final[dict[str, str]] = {
    "INSPECTION_NOT_EDITABLE": "inspection.error.not_editable",
    "REVIEW_PERMISSION_REQUIRED": "inspection.error.review_permission_required",
    "DUPLICATE_ANSWER": "inspection.error.duplicate_answer",
    "UNKNOWN_FIELD": "inspection.error.unknown_field",
    "ANSWER_INVALID": "inspection.error.answer_invalid",
    "FIELD_NOT_VISIBLE": "inspection.error.field_not_visible",
}

_REQUIRED: Final = "REQUIRED"  # the evaluator's code for a required field with no answer
_forms = FormsApi()


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _invalid(code: str, errors: list[dict[str, str]]) -> DomainError:
    return DomainError(422, code, messageKey=MESSAGE_KEYS[code], errors=errors)


@dataclass(frozen=True, slots=True)
class _Evaluated:
    """The current answers of one inspection and their evaluation (``submit`` mode)."""

    rows: dict[str, dict[str, Any]]
    evaluation: AnswerEvaluation

    @property
    def missing_required(self) -> list[str]:
        return [e.field_key for e in self.evaluation.errors if e.code == _REQUIRED]


async def _revision_schema(conn: AsyncConnection, row: Mapping[str, Any]) -> dict[str, Any]:
    revision = await _forms.get_revision(conn, row["template_revision_id"])
    if revision is None:  # a pinned revision is frozen and never deleted
        raise RuntimeError(f"inspection {row['id']}: pinned revision is not readable")
    return revision.schema


async def _evaluate_current(conn: AsyncConnection, row: Mapping[str, Any]) -> _Evaluated:
    rows = await repo.current_responses(conn, row["id"])
    answers = {key: r["value"] for key, r in rows.items()}
    evaluation = evaluate_answers(await _revision_schema(conn, row), answers, mode="submit")
    return _Evaluated(rows, evaluation)


async def current_responses(conn: AsyncConnection, row: Mapping[str, Any]) -> CurrentResponses:
    """The current answer per field of the inspection ``row`` and their evaluation."""
    current = await _evaluate_current(conn, row)
    evaluation = current.evaluation
    return CurrentResponses(
        answers={
            key: AnswerOut(
                value=r["value"],
                failed=r["failed"],
                responded_by=r["responded_by"],
                responded_at=r["responded_at"],
                response_id=r["id"],
            )
            for key, r in current.rows.items()
        },
        evaluation=AnswersEvaluation(
            visible=evaluation.visible,
            required=evaluation.required,
            missing_required=current.missing_required,
            failed=evaluation.failed,
        ),
    )


async def answer_facts(conn: AsyncConnection, row: Mapping[str, Any]) -> dict[str, int]:
    """The answer guard facts: answered fields, missing required, invalid and failed answers."""
    current = await _evaluate_current(conn, row)
    evaluation = current.evaluation
    answered = [
        key
        for key, r in current.rows.items()
        if evaluation.visible.get(key) and r["value"] not in (None, "", [])
    ]
    missing = current.missing_required
    return {
        "answeredCount": len(answered),
        "missingRequiredCount": len(missing),
        "invalidCount": len(evaluation.errors) - len(missing),
        "failedCount": len(evaluation.failed),
    }


class ResponseService:
    """Stateless apart from the policy service; the connection carries the tenant."""

    def __init__(self, policy: PolicyService) -> None:
        self._policy = policy

    async def _load_viewable(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> dict[str, Any]:
        row = await repo.get_inspection(conn, inspection_id)
        if row is None:  # another tenant's (RLS) or an unknown id: 404 before any permission
            raise NotFoundError(f"inspection {inspection_id} not found")
        resource = Resource(project_id=row["project_id"])
        await self._policy.assert_can(actor.principal, VIEW_PERMISSION, resource)
        return row

    async def _assert_editable(
        self, conn: AsyncConnection, actor: Actor, row: dict[str, Any]
    ) -> None:
        """ADR 0041 §6: who may save answers in the instance's current state."""
        state = await current_state(conn, row)
        needed = permissions_to_respond(state)
        if needed is None:
            raise DomainError(
                409,
                "INSPECTION_NOT_EDITABLE",
                messageKey=MESSAGE_KEYS["INSPECTION_NOT_EDITABLE"],
                state=state,
            )
        if REVIEW_EDIT_PERMISSION in needed:
            resource = Resource(project_id=row["project_id"])
            if not (
                await self._policy.can(actor.principal, REVIEW_EDIT_PERMISSION, resource)
            ).allowed:
                raise DomainError(
                    403,
                    "REVIEW_PERMISSION_REQUIRED",
                    messageKey=MESSAGE_KEYS["REVIEW_PERMISSION_REQUIRED"],
                    state=state,
                )

    async def submit(
        self,
        conn: AsyncConnection,
        actor: Actor,
        inspection_id: UUID,
        answers: Sequence[AnswerIn],
    ) -> list[ResponseResult]:
        """Store each new answer as one row; one result per answer, in the request's order."""
        row = await repo.lock_inspection(conn, inspection_id)  # (a)
        if row is None:
            raise NotFoundError(f"inspection {inspection_id} not found")
        resource = Resource(project_id=row["project_id"])
        await self._policy.assert_can(actor.principal, RESPOND_PERMISSION, resource)
        await self._assert_editable(conn, actor, row)  # (b)
        # INSPECTIONS-10 adds the section and report acknowledgement locks here, after the
        # state rules and before anything is validated or written.
        _assert_no_duplicates(answers)  # (b2)
        now = await repo.clock_timestamp(conn)  # after the lock: later than any earlier answer

        stored: dict[int, dict[str, Any]] = {}  # (c) idempotent retries, by request index
        for i, answer in enumerate(answers):
            existing = await repo.find_by_client_id(conn, inspection_id, answer.client_id)
            if existing is not None:
                stored[i] = existing
        new = [(i, a) for i, a in enumerate(answers) if i not in stored]

        results: dict[int, ResponseResult] = {
            i: ResponseResult(
                client_id=r["client_id"], response_id=r["id"], created=False, failed=r["failed"]
            )
            for i, r in stored.items()
        }
        if new:
            results.update(await self._insert(conn, actor, row, new, now))
        return [results[i] for i in range(len(answers))]

    async def _insert(
        self,
        conn: AsyncConnection,
        actor: Actor,
        row: dict[str, Any],
        new: list[tuple[int, AnswerIn]],
        now: datetime,
    ) -> dict[int, ResponseResult]:
        schema = await _revision_schema(conn, row)  # (d)
        field_keys = {f["key"] for section in schema["sections"] for f in section["fields"]}
        unknown = [
            {"path": f"answers[{i}].fieldKey", "code": "UNKNOWN_FIELD"}
            for i, a in new
            if a.field_key not in field_keys
        ]
        if unknown:
            raise _invalid("UNKNOWN_FIELD", unknown)

        current = await repo.current_responses(conn, row["id"])  # (e)
        merged: dict[str, Any] = {key: r["value"] for key, r in current.items()}
        merged.update({a.field_key: a.value for _, a in new})
        evaluation = evaluate_answers(schema, merged, mode="draft")
        hidden = [
            {"path": f"answers[{i}].fieldKey", "code": "FIELD_NOT_VISIBLE"}
            for i, a in new
            if not evaluation.visible.get(a.field_key, False)
        ]
        if hidden:
            raise _invalid("FIELD_NOT_VISIBLE", hidden)
        error_code = {e.field_key: e.code for e in evaluation.errors}
        invalid = [
            {"path": f"answers[{i}].value", "code": error_code[a.field_key]}
            for i, a in new
            if a.field_key in error_code
        ]
        if invalid:
            raise _invalid("ANSWER_INVALID", invalid)

        failed_fields = set(evaluation.failed)
        results: dict[int, ResponseResult] = {}
        for i, answer in new:  # (f)
            previous = current.get(answer.field_key)
            failed = answer.field_key in failed_fields
            inserted = await repo.insert_response(
                conn,
                {
                    "id": _new_id(),
                    "tenant_id": actor.principal.tenant_id,
                    "inspection_id": row["id"],
                    "field_key": answer.field_key,
                    "value": answer.value,
                    "failed": failed,
                    "revision_id": row["template_revision_id"],
                    "client_id": answer.client_id,
                    "supersedes_id": None if previous is None else previous["id"],
                    "responded_by": actor.principal.actor_id,
                    "responded_at": now,
                    "created_at": now,
                },
            )
            if emits_answer_failed(None if previous is None else previous["failed"], failed):
                await _emit_answer_failed(conn, row, inserted)  # (g)
            results[i] = ResponseResult(
                client_id=answer.client_id, response_id=inserted["id"], created=True, failed=failed
            )
        return results

    async def current(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> CurrentResponses:
        """The current answers and their evaluation (``inspection.view``)."""
        row = await self._load_viewable(conn, actor, inspection_id)
        return await current_responses(conn, row)

    async def history(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID, field_key: str
    ) -> list[ResponseEntry]:
        """Every response for one field, oldest first (``inspection.view``)."""
        await self._load_viewable(conn, actor, inspection_id)
        rows = await repo.field_history(conn, inspection_id, field_key)
        return [ResponseEntry.model_validate(r) for r in rows]


def _assert_no_duplicates(answers: Sequence[AnswerIn]) -> None:
    """One batch names each field and each client id at most once."""
    fields: set[str] = set()
    clients: set[UUID] = set()
    repeated: list[dict[str, str]] = []
    for i, answer in enumerate(answers):
        if answer.field_key in fields or answer.client_id in clients:
            repeated.append({"path": f"answers[{i}]", "code": "DUPLICATE_ANSWER"})
        fields.add(answer.field_key)
        clients.add(answer.client_id)
    if repeated:
        raise _invalid("DUPLICATE_ANSWER", repeated)


async def _emit_answer_failed(
    conn: AsyncConnection, row: Mapping[str, Any], response: Mapping[str, Any]
) -> None:
    payload = {
        "inspectionId": str(row["id"]),
        "responseId": str(response["id"]),
        "fieldKey": response["field_key"],
        "assetId": str(row["asset_id"]),
        "projectId": None if row["project_id"] is None else str(row["project_id"]),
    }
    await emit(
        conn,
        INSPECTION_ANSWER_FAILED,
        1,
        Aggregate(RECORD_TYPE, row["id"]),
        payload,
        asset_id=row["asset_id"],
    )
