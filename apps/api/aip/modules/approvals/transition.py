"""The one server-side transition path (APPROVALS-02, ADR 0010, ADR 0035).

``TransitionService.transition`` runs on the caller's ``with_tenant`` connection, so the decision
row, the instance update and the outbox event commit or roll back together:

a. lock the instance (``FOR UPDATE``); none in this tenant is 404 (another tenant's is invisible
   under RLS). The caller needs ``approvals.view`` on it (403), and a stale
   ``expected_sync_version`` is 409 ``VERSION_CONFLICT``;
b. load the definition the instance is pinned to, never the active one;
c. ``apply_transition``; an illegal action is 409 ``INVALID_TRANSITION``;
d. ``PolicyService`` for the transition's ``requiredPermission`` on the instance's project (403);
   while a critical decision waits for a countersign, only that action may be taken (409
   ``COUNTERSIGN_PENDING``), and never by the person who made it (409 ``SELF_COUNTERSIGN``);
e. the JSONLogic guard over host-module facts (Part B): false is 422 ``GUARD_FAILED``, a provider
   or evaluation error is 422 ``GUARD_ERROR`` (fail closed). It runs before the sign-off check so
   nobody is asked to step up for a transition the guard refuses (ADR 0035);
f. a ``critical`` transition asks identity's ``check_signoff_assurance``: ``step_up_required`` is
   401 ``STEP_UP_REQUIRED`` (ADR 0034); ``countersign_required`` records the decision as
   ``pending_countersign`` without moving the instance (a countersigner must get ``allow``,
   else 403 ``COUNTERSIGN_ASSURANCE_REQUIRED``);
g. append the hash-chained decision (``seq = last + 1``) with the signer's assurance and IP;
h. move ``current_state`` with ``update_with_version`` and emit ``workflow.transitioned`` v1.

Nothing is written before every check has passed. ``describe`` returns the instance with each
transition from its state and whether this caller may take it (``allowed``/``reasonKey``),
computed with the same permission, countersign and guard rules; it is a hint, ``transition``
decides.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import rfc8785
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.api import role_codes
from aip.modules.approvals import repository as repo
from aip.modules.approvals.decision_chain import (
    ChainBroken,
    ChainOk,
    entry_hash,
    genesis_hash,
    sha256_hex,
    verify_chain,
)
from aip.modules.approvals.engine.evaluator import TransitionRejected, apply_transition
from aip.modules.approvals.errors import NoActiveDefinitionError
from aip.modules.approvals.events import WORKFLOW_TRANSITIONED, WorkflowTransitioned
from aip.modules.approvals.guards.context_providers import provider_for, resolver_for
from aip.modules.approvals.guards.jsonlogic import GuardError, evaluate_guard, truthy
from aip.modules.approvals.schemas import TransitionSpec, WorkflowDefinition
from aip.modules.approvals.service import InstancesService, definition_from_row, new_id
from aip.modules.approvals.tables import workflow_instances
from aip.modules.identity.api import (
    Assurance,
    SessionFacts,
    SignoffContext,
    StepUpRequiredError,
    check_signoff_assurance,
    derive_assurance,
    mfa_enrolled_at,
)
from aip.platform.access import AccessPrincipal, PolicyService, Resource
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.errors import ConflictError, NotFoundError
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "START_PERMISSION",
    "VIEW_PERMISSION",
    "Actor",
    "Availability",
    "History",
    "InstanceView",
    "TransitionResult",
    "TransitionService",
]

logger = logging.getLogger(__name__)

VIEW_PERMISSION: Final = "approvals.view"
START_PERMISSION: Final = "approvals.start"
GUARD_FAILED_KEY: Final = "approvals.guard.failed"
GUARD_ERROR_KEY: Final = "approvals.guard.error"
NO_PERMISSION_KEY: Final = "approvals.permission.denied"
COUNTERSIGN_PENDING_KEY: Final = "approvals.countersign.pending"
SELF_COUNTERSIGN_KEY: Final = "approvals.countersign.self"

# How the signer authenticated, in the data model's ``auth_strength`` vocabulary.
_AUTH_STRENGTH: Final = {
    "password": "password",
    "device_pin": "pin",
    "passkey": "mfa",
    "totp": "mfa",
    "idp_mfa": "mfa",
}


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is acting: the policy's principal, the session's authentication and the client IP."""

    principal: AccessPrincipal
    session: SessionFacts
    ip_address: str | None = None
    return_to: str | None = None  # where a step-up sends the browser back to


@dataclass(frozen=True, slots=True)
class Availability:
    transition: TransitionSpec
    allowed: bool
    reason_key: str | None


@dataclass(frozen=True, slots=True)
class InstanceView:
    instance: dict[str, Any]
    definition: WorkflowDefinition
    pending_countersign: str | None
    available: list[Availability]


@dataclass(frozen=True, slots=True)
class TransitionResult:
    view: InstanceView
    decision: dict[str, Any]

    @property
    def applied(self) -> bool:
        return self.decision["status"] == "applied"


@dataclass(frozen=True, slots=True)
class History:
    entries: list[dict[str, Any]]
    chain: ChainOk | ChainBroken


class _FactsError(Exception):
    """A guard context provider failed or returned something that is not JSON."""


def _resource(instance: RowMapping | dict[str, Any]) -> Resource:
    return Resource(project_id=instance["project_id"])


def _json_scalar(value: object) -> object:
    """``json.dumps`` default: numbers stay numbers, dates become ISO strings, the rest refuse."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError("non-finite number in guard facts")
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not a JSON value")


def _json_facts(facts: object) -> dict[str, Any]:
    """The provider's facts as plain JSON; anything else fails closed (``GUARD_ERROR``)."""
    if not isinstance(facts, dict):
        raise _FactsError("a guard context provider must return an object")
    try:
        return json.loads(json.dumps(facts, default=_json_scalar, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise _FactsError(type(exc).__name__) from exc


def _pending(last: RowMapping | None) -> RowMapping | None:
    return last if last is not None and last["status"] == "pending_countersign" else None


class TransitionService:
    """Stateless apart from the policy service; the connection carries the tenant."""

    def __init__(self, policy: PolicyService, instances: InstancesService | None = None) -> None:
        self._policy = policy
        self._instances = instances or InstancesService()

    # --- reads --------------------------------------------------------------------------------

    async def _load(
        self, conn: AsyncConnection, actor: Actor, instance_id: UUID, *, for_update: bool = False
    ) -> RowMapping:
        row = await repo.get_instance_by_id(conn, instance_id, for_update=for_update)
        if row is None:
            raise NotFoundError(f"workflow instance {instance_id} not found")
        await self._policy.assert_can(actor.principal, VIEW_PERMISSION, _resource(row))
        return row

    async def _guard_data(
        self, conn: AsyncConnection, actor: Actor, instance: RowMapping | dict[str, Any]
    ) -> dict[str, Any]:
        provider = provider_for(instance["record_type"])
        record: dict[str, Any] = {}
        if provider is not None:
            try:
                # A savepoint: a provider's SQL error must not abort the transition's transaction.
                async with conn.begin_nested():
                    facts = await provider(conn, instance["record_id"])
                record = _json_facts(facts)
            except _FactsError:
                raise
            except Exception as exc:
                raise _FactsError(type(exc).__name__) from exc
        actor_id = actor.principal.actor_id
        roles = [] if actor_id is None else await role_codes(conn, actor_id, instance["project_id"])
        project_id = instance["project_id"]
        return {
            "record": record,
            "actor": {"id": None if actor_id is None else str(actor_id), "roles": roles},
            "instance": {
                "state": instance["current_state"],
                "projectId": None if project_id is None else str(project_id),
                "recordType": instance["record_type"],
            },
        }

    async def _view(
        self, conn: AsyncConnection, actor: Actor, instance: RowMapping | dict[str, Any]
    ) -> InstanceView:
        definition = definition_from_row(await repo.get_definition(conn, instance["definition_id"]))
        pending = _pending(await repo.last_decision(conn, instance["id"]))
        candidates = [
            t for t in definition.spec.transitions if t.from_state == instance["current_state"]
        ]
        data: dict[str, Any] | None = None
        facts_failed = False
        if any(t.guard is not None for t in candidates):
            try:
                data = await self._guard_data(conn, actor, instance)
            except _FactsError:
                facts_failed = True
        available: list[Availability] = []
        for t in candidates:
            available.append(
                Availability(
                    t, *await self._why_not(actor, instance, t, pending, data, facts_failed)
                )
            )
        return InstanceView(
            instance=dict(instance),
            definition=definition,
            pending_countersign=None if pending is None else str(pending["action"]),
            available=available,
        )

    async def _why_not(
        self,
        actor: Actor,
        instance: RowMapping | dict[str, Any],
        t: TransitionSpec,
        pending: RowMapping | None,
        data: dict[str, Any] | None,
        facts_failed: bool,
    ) -> tuple[bool, str | None]:
        decision = await self._policy.can(
            actor.principal, t.required_permission, _resource(instance)
        )
        if not decision.allowed:
            return False, NO_PERMISSION_KEY
        if pending is not None:
            if pending["action"] != t.action:
                return False, COUNTERSIGN_PENDING_KEY
            if pending["actor_id"] == actor.principal.actor_id:
                return False, SELF_COUNTERSIGN_KEY
        if t.guard is not None:
            if facts_failed or data is None:
                return False, GUARD_ERROR_KEY
            try:
                passed = truthy(evaluate_guard(t.guard, data))
            except GuardError:
                return False, GUARD_ERROR_KEY
            if not passed:
                return False, t.guard_message_key or GUARD_FAILED_KEY
        return True, None

    async def describe(
        self, conn: AsyncConnection, actor: Actor, instance_id: UUID
    ) -> InstanceView:
        """The instance, its pinned version and what this caller may do next."""
        return await self._view(conn, actor, await self._load(conn, actor, instance_id))

    async def history(self, conn: AsyncConnection, actor: Actor, instance_id: UUID) -> History:
        """Every decision in ``seq`` order and whether the hash chain still holds."""
        await self._load(conn, actor, instance_id)
        entries = [dict(r) for r in await repo.list_decisions(conn, instance_id)]
        return History(entries=entries, chain=verify_chain(entries))

    # --- writes -------------------------------------------------------------------------------

    async def start(
        self,
        conn: AsyncConnection,
        actor: Actor,
        record_type: str,
        record_id: UUID,
        project_id: UUID | None,
    ) -> InstanceView:
        """The record's instance (started on the active definition if it has none yet)."""
        await self._policy.assert_can(
            actor.principal, START_PERMISSION, Resource(project_id=project_id)
        )
        try:
            started = await self._instances.start_instance(conn, record_type, record_id, project_id)
        except NoActiveDefinitionError:
            raise DomainError(422, "NO_ACTIVE_DEFINITION") from None
        return await self.describe(conn, actor, started.id)

    async def start_for_client(
        self,
        conn: AsyncConnection,
        actor: Actor,
        record_type: str,
        record_id: UUID,
        claimed_project_id: UUID | None,
    ) -> InstanceView:
        """``start`` for a request body: the record's project comes from its host module's
        resolver (422 ``UNKNOWN_RECORD_TYPE`` without one, 404 when the record is not visible),
        and a ``projectId`` that disagrees is 422 ``PROJECT_MISMATCH``."""
        resolver = resolver_for(record_type)
        if resolver is None:
            raise DomainError(422, "UNKNOWN_RECORD_TYPE")
        ref = await resolver(conn, record_id)
        if ref is None:
            raise NotFoundError(f"{record_type} {record_id} not found")
        if claimed_project_id is not None and claimed_project_id != ref.project_id:
            raise DomainError(422, "PROJECT_MISMATCH")
        return await self.start(conn, actor, record_type, record_id, ref.project_id)

    async def _check_guard(
        self, conn: AsyncConnection, actor: Actor, instance: RowMapping, t: TransitionSpec
    ) -> dict[str, Any] | None:
        if t.guard is None:
            return None
        try:
            data = await self._guard_data(conn, actor, instance)
            value = evaluate_guard(t.guard, data)
            facts_hash = sha256_hex(rfc8785.dumps(data))
        except (_FactsError, GuardError, rfc8785.CanonicalizationError) as exc:
            # Never log the facts: they are another module's record data.
            logger.warning(
                "workflow guard error on instance %s (%s): %s", instance["id"], t.action, exc
            )
            raise DomainError(422, "GUARD_ERROR", messageKey=GUARD_ERROR_KEY) from None
        if not truthy(value):
            raise DomainError(
                422, "GUARD_FAILED", messageKey=t.guard_message_key or GUARD_FAILED_KEY
            )
        return {"passed": True, "guard": t.guard, "factsHash": facts_hash}

    async def _signoff(
        self, conn: AsyncConnection, actor: Actor, t: TransitionSpec, pending: RowMapping | None
    ) -> tuple[Assurance, str]:
        """The signer's assurance and the decision's status; raises when it may not proceed."""
        if not t.critical:
            return derive_assurance(actor.session), "applied"
        actor_id = actor.principal.actor_id
        enrolled = actor_id is not None and await mfa_enrolled_at(conn, actor_id) is not None
        ctx = SignoffContext(
            session=actor.session,
            aal2_available=actor.session.aal >= 2 or enrolled,
            now=datetime.now(UTC),
        )
        decision = await check_signoff_assurance(
            conn, ctx, t.signoff_action or f"workflow.{t.action}"
        )
        if decision.decision == "step_up_required":
            raise StepUpRequiredError(actor.return_to)
        if decision.decision == "countersign_required":
            if pending is not None:
                raise DomainError(403, "COUNTERSIGN_ASSURANCE_REQUIRED")
            return decision.assurance, "pending_countersign"
        return decision.assurance, "applied"

    async def transition(
        self,
        conn: AsyncConnection,
        actor: Actor,
        instance_id: UUID,
        action: str,
        *,
        comment: str | None = None,
        expected_sync_version: int | None = None,
    ) -> TransitionResult:
        """Take ``action`` on the instance; see the module docstring for every refusal."""
        instance = await self._load(conn, actor, instance_id, for_update=True)  # (a)
        if expected_sync_version is not None and expected_sync_version != instance["sync_version"]:
            raise ConflictError(dict(instance))
        definition = definition_from_row(  # (b)
            await repo.get_definition(conn, instance["definition_id"])
        )
        outcome = apply_transition(definition.spec, instance["current_state"], action)  # (c)
        if isinstance(outcome, TransitionRejected):
            raise DomainError(409, outcome.error)
        t = outcome.transition
        await self._policy.assert_can(actor.principal, t.required_permission, _resource(instance))
        last = await repo.last_decision(conn, instance_id)  # (d)
        pending = _pending(last)
        if pending is not None:
            if pending["action"] != action:
                raise DomainError(409, "COUNTERSIGN_PENDING")
            if pending["actor_id"] == actor.principal.actor_id:
                raise DomainError(409, "SELF_COUNTERSIGN")
        guard_result = await self._check_guard(conn, actor, instance, t)  # (e)
        assurance, status = await self._signoff(conn, actor, t, pending)  # (f)

        entry: dict[str, Any] = {  # (g)
            "id": new_id(),
            "tenant_id": actor.principal.tenant_id,
            "instance_id": instance_id,
            "step_id": None,
            "seq": 1 if last is None else int(last["seq"]) + 1,
            "from_state": outcome.from_state,
            "to_state": outcome.to_state,
            "action": action,
            "actor_id": actor.principal.actor_id,
            "on_behalf_of": None,
            "comment": comment,
            "auth_strength": _AUTH_STRENGTH[assurance.method],
            "ip_address": actor.ip_address,
            "guard_result": guard_result,
            "status": status,
            "countersigns_id": None if pending is None else pending["id"],
            "assurance_level": assurance.level,
            "assurance_method": assurance.method,
            "authenticated_at": assurance.authenticated_at,
            "device_id": assurance.device_id,
            "prev_hash": genesis_hash(instance_id) if last is None else str(last["entry_hash"]),
            "created_at": datetime.now(UTC),
        }
        entry["entry_hash"] = entry_hash(entry)
        await repo.insert_decision(conn, entry)

        # (h) A pending decision still bumps sync_version: the instance now waits for a countersign.
        patch = {"current_state": outcome.to_state} if status == "applied" else {}
        updated = await update_with_version(
            conn, workflow_instances, instance_id, int(instance["sync_version"]), patch
        )
        if status == "applied":
            payload = WorkflowTransitioned.model_validate(
                {
                    "instanceId": instance_id,
                    "recordType": instance["record_type"],
                    "recordId": instance["record_id"],
                    "projectId": instance["project_id"],
                    "from": outcome.from_state,
                    "to": outcome.to_state,
                    "action": action,
                    "actorId": actor.principal.actor_id,
                    "definitionKey": definition.key,
                    "definitionVersion": definition.version,
                }
            ).model_dump(mode="json")
            await emit(
                conn, WORKFLOW_TRANSITIONED, 1, Aggregate("workflow_instance", instance_id), payload
            )
        current = {
            **dict(instance),
            "current_state": updated["current_state"],
            "sync_version": updated["sync_version"],
        }
        return TransitionResult(view=await self._view(conn, actor, current), decision=entry)
