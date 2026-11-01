"""Approval routes on workflow instances (APPROVALS-04, ADR 0040).

Every method runs on the caller's ``with_tenant`` connection, so the steps, the decision row, the
instance update and the outbox events commit or roll back together; RLS keeps each tenant to its
own rows, so another tenant's instance or template is 404.

- ``create_template`` (``approvals.design``, tenant-wide): validates the route shape
  (``route_plan.groups``; 422 ``ROUTE_SHAPE_INVALID``) and that each role or team approver exists
  (422 ``UNKNOWN_APPROVER``). Templates are immutable once created.
- ``start_route`` (``approvals.start`` on the instance's project): 404 for an unknown template;
  409 ``ROUTE_ACTIVE`` while a route runs; 422 ``ROUTE_TEMPLATE_MISMATCH`` for another record
  type; 422 ``ROUTE_ACTION_INVALID`` unless both route actions are transitions from the current
  state of the pinned definition; 409 ``COUNTERSIGN_PENDING`` while a decision waits. Copies the
  template steps into a new round, activates the first group (``due_at = now + due_hours``) and
  emits ``approval.requested`` v1 per activated step. The route's submitter, whom separation of
  duties keeps from deciding, is the actor of the instance's last applied decision, else whoever
  starts the route.
- ``decide`` (``approvals.view`` and ``approvals.approve`` on the instance's project), on the
  locked instance: 404 for a step not on its current round; 409 ``STEP_NOT_PENDING`` once decided
  or skipped; 403 ``NOT_CURRENT_APPROVER`` while it waits or when the actor is not eligible now;
  403 ``SELF_APPROVAL_FORBIDDEN`` for the submitter unless the template allows it; 422
  ``COMMENT_REQUIRED`` for a reject without a comment. Then ``route_plan.next_action``: a
  finishing decision takes the template's action through ``TransitionService.complete_route``
  and emits ``approval.approved``/``approval.rejected`` and ``approval.completed``; any other
  appends a non-moving ``approve_step`` row and may activate the next group.
- ``route`` (``approvals.view``) returns the latest round; ``pending_steps`` is the inbox query
  (APPROVALS-06): pending steps the actor is eligible for now, on instances they may view.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access.api import get_team_ref, role_code_for_id, teams_for_user
from aip.modules.approvals import repository as repo
from aip.modules.approvals.events import (
    APPROVAL_APPROVED,
    APPROVAL_COMPLETED,
    APPROVAL_REJECTED,
    APPROVAL_REQUESTED,
    ApprovalCompleted,
    ApprovalOutcome,
    ApprovalRequested,
)
from aip.modules.approvals.routes_engine import repository as route_repo
from aip.modules.approvals.routes_engine.eligibility import AccessDirectory, is_eligible
from aip.modules.approvals.routes_engine.route_plan import (
    Activate,
    Complete,
    Decision,
    PlanStep,
    RouteShapeError,
    first_group,
    groups,
    next_action,
)
from aip.modules.approvals.schemas import RouteTemplateCreate
from aip.modules.approvals.service import new_id
from aip.modules.approvals.tables import workflow_instances
from aip.modules.approvals.transition import (
    START_PERMISSION,
    VIEW_PERMISSION,
    Actor,
    InstanceView,
    TransitionService,
)
from aip.platform.access import PolicyService, Resource
from aip.platform.context import ContextMissingError, get_context
from aip.platform.db.concurrency import update_with_version
from aip.platform.db.errors import NotFoundError
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "APPROVE_PERMISSION",
    "DESIGN_PERMISSION",
    "DecideResult",
    "PendingStep",
    "RouteTemplate",
    "RouteView",
    "RoutesService",
]

DESIGN_PERMISSION: Final = "approvals.design"
APPROVE_PERMISSION: Final = "approvals.approve"
COMMENT_REQUIRED_KEY: Final = "approvals.comment.required"
_STEP_ACTIONS: Final[dict[Decision, str]] = {"approve": "approve_step", "reject": "reject_step"}


@dataclass(frozen=True, slots=True)
class RouteTemplate:
    template: dict[str, Any]
    steps: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class RouteView:
    view: InstanceView
    steps: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class DecideResult:
    route: RouteView
    decision: dict[str, Any]
    outcome: Literal["approved", "rejected"] | None


@dataclass(frozen=True, slots=True)
class PendingStep:
    step: dict[str, Any]
    record_type: str
    record_id: UUID
    project_id: UUID | None
    current_state: str


def _resource(instance: RowMapping | dict[str, Any]) -> Resource:
    return Resource(project_id=instance["project_id"])


def _plan(steps: Sequence[RowMapping | dict[str, Any]]) -> list[PlanStep]:
    return [PlanStep(s["id"], s["step_order"], s["mode"], s["status"]) for s in steps]


def _context_actor() -> UUID | None:
    try:
        return get_context().actor_id
    except ContextMissingError:
        return None


def _first_pending(steps: Sequence[RowMapping | dict[str, Any]]) -> UUID | None:
    return next((s["id"] for s in steps if s["status"] == "pending"), None)


class RoutesService:
    """Stateless apart from the policy service; the connection carries the tenant."""

    def __init__(self, policy: PolicyService, transitions: TransitionService | None = None) -> None:
        self._policy = policy
        self._transitions = transitions or TransitionService(policy)

    # --- templates ----------------------------------------------------------------------------

    async def create_template(
        self, conn: AsyncConnection, actor: Actor, body: RouteTemplateCreate
    ) -> RouteTemplate:
        await self._policy.assert_can(actor.principal, DESIGN_PERMISSION, Resource())
        try:
            groups([PlanStep(new_id(), s.step_order, s.mode) for s in body.steps])
        except RouteShapeError:
            raise DomainError(422, "ROUTE_SHAPE_INVALID") from None
        for step in body.steps:
            if step.approver_type == "role":
                known = await role_code_for_id(conn, step.approver_ref) is not None
            elif step.approver_type == "team":
                known = await get_team_ref(conn, step.approver_ref) is not None
            else:
                known = True  # users are checked at decision time (only they can decide)
            if not known:
                raise DomainError(422, "UNKNOWN_APPROVER")
        template = await route_repo.insert_template(
            conn,
            id=new_id(),
            name=body.name.strip(),
            record_type=body.record_type,
            on_approved_action=body.on_approved_action,
            on_rejected_action=body.on_rejected_action,
            allow_self_approval=body.allow_self_approval,
            created_by=actor.principal.actor_id or _context_actor(),
        )
        steps = [
            dict(
                await route_repo.insert_template_step(
                    conn,
                    id=new_id(),
                    route_template_id=template["id"],
                    step_order=s.step_order,
                    mode=s.mode,
                    approver_type=s.approver_type,
                    approver_ref=s.approver_ref,
                    due_hours=s.due_hours,
                )
            )
            for s in sorted(body.steps, key=lambda s: s.step_order)
        ]
        return RouteTemplate(template=dict(template), steps=steps)

    async def list_templates(self, conn: AsyncConnection, actor: Actor) -> list[RouteTemplate]:
        await self._policy.assert_can(actor.principal, DESIGN_PERMISSION, Resource())
        templates = await route_repo.list_templates(conn)
        steps = await route_repo.template_steps(conn, [t["id"] for t in templates])
        return [
            RouteTemplate(
                template=dict(t),
                steps=[dict(s) for s in steps if s["route_template_id"] == t["id"]],
            )
            for t in templates
        ]

    # --- routes on instances ------------------------------------------------------------------

    async def route(self, conn: AsyncConnection, actor: Actor, instance_id: UUID) -> RouteView:
        """The instance and its latest round of steps (``approvals.view``)."""
        instance = await self._transitions.load(conn, actor, instance_id)
        return await self._route_view(conn, actor, instance)

    async def _route_view(
        self, conn: AsyncConnection, actor: Actor, instance: RowMapping | dict[str, Any]
    ) -> RouteView:
        steps = await route_repo.round_steps(conn, instance["id"], int(instance["route_round"]))
        return RouteView(
            view=await self._transitions.view(conn, actor, instance),
            steps=[dict(s) for s in steps],
        )

    async def start_route(
        self, conn: AsyncConnection, actor: Actor, instance_id: UUID, route_template_id: UUID
    ) -> RouteView:
        instance = await self._transitions.load(conn, actor, instance_id, for_update=True)
        await self._policy.assert_can(actor.principal, START_PERMISSION, _resource(instance))
        template = await route_repo.get_template(conn, route_template_id)
        if template is None or template["deleted_at"] is not None:
            raise NotFoundError(f"route template {route_template_id} not found")
        if template["record_type"] != instance["record_type"]:
            raise DomainError(422, "ROUTE_TEMPLATE_MISMATCH")
        if instance["current_step_id"] is not None:
            raise DomainError(409, "ROUTE_ACTIVE")
        definition = await self._transitions.pinned_definition(conn, instance)
        state = instance["current_state"]
        legal = {t.action for t in definition.spec.transitions if t.from_state == state}
        if not {template["on_approved_action"], template["on_rejected_action"]} <= legal:
            raise DomainError(422, "ROUTE_ACTION_INVALID")
        last = await repo.last_decision(conn, instance_id)
        if last is not None and last["status"] == "pending_countersign":
            raise DomainError(409, "COUNTERSIGN_PENDING")

        route_round = int(instance["route_round"]) + 1
        template_steps = await route_repo.template_steps(conn, [route_template_id])
        steps = [
            await route_repo.insert_instance_step(
                conn,
                id=new_id(),
                route_template_id=route_template_id,
                instance_id=instance_id,
                route_round=route_round,
                step_order=s["step_order"],
                mode=s["mode"],
                approver_type=s["approver_type"],
                approver_ref=s["approver_ref"],
                due_hours=s["due_hours"],
            )
            for s in template_steps
        ]
        activated = await route_repo.activate_group(
            conn, instance_id, route_round, first_group(_plan(steps))
        )
        submitter = (
            last["actor_id"]
            if last is not None and last["actor_id"] is not None
            else actor.principal.actor_id
        )
        patch = {
            "route_template_id": route_template_id,
            "route_round": route_round,
            "current_step_id": _first_pending(activated),
            "route_submitted_by": submitter,
        }
        updated = await self._update(conn, instance, patch)
        await self._emit_requested(conn, instance, activated)
        return await self._route_view(conn, actor, updated)

    async def decide(
        self,
        conn: AsyncConnection,
        actor: Actor,
        instance_id: UUID,
        step_id: UUID,
        decision: Decision,
        comment: str | None = None,
    ) -> DecideResult:
        instance = await self._transitions.load(conn, actor, instance_id, for_update=True)
        await self._policy.assert_can(actor.principal, APPROVE_PERMISSION, _resource(instance))
        route_round = int(instance["route_round"])
        steps = await route_repo.round_steps(conn, instance_id, route_round)
        step = next((s for s in steps if s["id"] == step_id), None)
        if step is None:
            raise NotFoundError(f"approval step {step_id} not found")
        if step["status"] == "waiting":
            raise DomainError(403, "NOT_CURRENT_APPROVER")
        if step["status"] != "pending":
            raise DomainError(409, "STEP_NOT_PENDING")
        actor_id = actor.principal.actor_id
        eligible = await is_eligible(
            AccessDirectory(conn),
            actor_id,
            step["approver_type"],
            step["approver_ref"],
            instance["project_id"],
        )
        if not eligible:
            raise DomainError(403, "NOT_CURRENT_APPROVER")
        template = await route_repo.get_template(conn, step["route_template_id"])
        if template is None:  # a template is never hard-deleted
            raise NotFoundError(f"route template {step['route_template_id']} not found")
        if not template["allow_self_approval"] and actor_id == instance["route_submitted_by"]:
            raise DomainError(403, "SELF_APPROVAL_FORBIDDEN")
        if decision == "reject" and not (comment and comment.strip()):
            raise DomainError(422, "COMMENT_REQUIRED", messageKey=COMMENT_REQUIRED_KEY)

        plan = next_action(_plan(steps), step_id, decision)
        await route_repo.decide_step(
            conn, step_id, "approved" if decision == "approve" else "rejected", actor_id
        )
        if isinstance(plan, Complete):
            await route_repo.skip_steps(conn, plan.skip)
            approved = plan.outcome == "approved"
            action = template["on_approved_action" if approved else "on_rejected_action"]
            entry, updated = await self._transitions.complete_route(
                conn,
                actor,
                instance,
                action,
                comment=comment,
                step_id=step_id,
                patch={"current_step_id": None},
            )
            await self._emit_outcome(conn, instance, template, step_id, actor_id, action, plan)
            return DecideResult(
                route=await self._route_view(conn, actor, {**dict(instance), **updated}),
                decision=entry,
                outcome=plan.outcome,
            )

        activated: list[RowMapping] = []
        if isinstance(plan, Activate):
            activated = await route_repo.activate_group(conn, instance_id, route_round, plan.order)
        after = await route_repo.round_steps(conn, instance_id, route_round)
        entry, updated = await self._transitions.record_step_decision(
            conn,
            actor,
            instance,
            _STEP_ACTIONS[decision],
            comment=comment,
            step_id=step_id,
            patch={"current_step_id": _first_pending(after)},
        )
        await self._emit_requested(conn, instance, activated)
        return DecideResult(
            route=await self._route_view(conn, actor, {**dict(instance), **updated}),
            decision=entry,
            outcome=None,
        )

    async def pending_steps(
        self, conn: AsyncConnection, actor: Actor, *, limit: int = 200
    ) -> list[PendingStep]:
        """The pending steps ``actor`` may decide now, on instances they may view (the inbox)."""
        user_id = actor.principal.actor_id
        if user_id is None:
            return []
        team_ids = [t.id for t in await teams_for_user(conn, user_id)]
        directory = AccessDirectory(conn)
        found: list[PendingStep] = []
        for row in await route_repo.pending_candidates(conn, user_id, team_ids, limit):
            eligible = await is_eligible(
                directory, user_id, row["approver_type"], row["approver_ref"], row["project_id"]
            )
            if not eligible:
                continue
            resource = Resource(project_id=row["project_id"])
            viewable = await self._policy.can(actor.principal, VIEW_PERMISSION, resource)
            if not viewable.allowed:
                continue
            found.append(
                PendingStep(
                    step={k: row[k] for k in row if k not in _INSTANCE_KEYS},
                    record_type=row["record_type"],
                    record_id=row["record_id"],
                    project_id=row["project_id"],
                    current_state=row["current_state"],
                )
            )
        return found

    # --- helpers ------------------------------------------------------------------------------

    async def _update(
        self, conn: AsyncConnection, instance: RowMapping, patch: dict[str, Any]
    ) -> dict[str, Any]:
        updated = await update_with_version(
            conn, workflow_instances, instance["id"], int(instance["sync_version"]), patch
        )
        return {**dict(instance), **{k: updated[k] for k in (*patch, "sync_version")}}

    async def _emit_requested(
        self, conn: AsyncConnection, instance: RowMapping, steps: Sequence[RowMapping]
    ) -> None:
        for step in steps:
            payload = ApprovalRequested(
                instance_id=instance["id"],
                step_id=step["id"],
                record_type=instance["record_type"],
                record_id=instance["record_id"],
                project_id=instance["project_id"],
                approver_type=step["approver_type"],
                approver_ref=step["approver_ref"],
                due_at=step["due_at"],
            ).model_dump(mode="json")
            await emit(
                conn,
                APPROVAL_REQUESTED,
                1,
                Aggregate("workflow_instance", instance["id"]),
                payload,
            )

    async def _emit_outcome(
        self,
        conn: AsyncConnection,
        instance: RowMapping,
        template: RowMapping,
        step_id: UUID,
        actor_id: UUID | None,
        action: str,
        plan: Complete,
    ) -> None:
        aggregate = Aggregate("workflow_instance", instance["id"])
        outcome = ApprovalOutcome(
            instance_id=instance["id"],
            record_type=instance["record_type"],
            record_id=instance["record_id"],
            project_id=instance["project_id"],
            route_template_id=template["id"],
            step_id=step_id,
            actor_id=actor_id,
            action=action,
        ).model_dump(mode="json")
        name = APPROVAL_APPROVED if plan.outcome == "approved" else APPROVAL_REJECTED
        await emit(conn, name, 1, aggregate, outcome)
        completed = ApprovalCompleted(
            instance_id=instance["id"],
            record_type=instance["record_type"],
            record_id=instance["record_id"],
            outcome=plan.outcome,
        ).model_dump(mode="json")
        await emit(conn, APPROVAL_COMPLETED, 1, aggregate, completed)


_INSTANCE_KEYS: Final = frozenset({"record_type", "record_id", "project_id", "current_state"})
