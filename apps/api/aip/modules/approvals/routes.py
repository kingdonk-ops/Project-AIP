"""HTTP routes for approvals (APPROVALS-02), mounted under ``/api/v1/approvals``.

- ``POST /instances`` starts (or returns) a record's workflow (``approvals.start``);
- ``GET /instances/{id}`` returns its state, pinned version and ``availableTransitions`` for the
  caller (``approvals.view``);
- ``POST /instances/{id}/transition`` takes an action (``approvals.view`` plus the transition's own
  ``requiredPermission``); 200 when it took effect, 202 when it waits for a countersign;
- ``GET /instances/{id}/history`` returns the decisions and ``chainValid`` (``approvals.view``).

Every route is ``authenticated()`` and the service checks each permission against the instance's
project, which is known only once the instance is loaded (deny by default either way). Another
tenant's instance is 404. Bodies forbid unknown keys (422), so a client cannot send a guard
outcome. Explicit ``operation_id``s keep the generated client's hook names stable.

TESTING-13 also mounts ``demo.router``: the dev/test-only ``approvals_demo`` fixture switch,
hidden from the OpenAPI document and 404 outside development, test and demo (see ``demo.py``).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from aip.modules.approvals import demo
from aip.modules.approvals.decision_chain import ChainBroken
from aip.modules.approvals.schemas import (
    ApprovalsErrorBody,
    AssuranceOut,
    AvailableTransition,
    DecisionOut,
    HistoryOut,
    InstanceOut,
    InstanceStart,
    TransitionOut,
    TransitionRequest,
)
from aip.modules.approvals.transition import Actor, InstanceView, TransitionService
from aip.modules.identity.api import Principal, SessionFacts, get_principal
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, PolicyService, authenticated, current_principal
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant

__all__ = ["router"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ApprovalsErrorBody, "description": "Not signed in, or STEP_UP_REQUIRED"},
    403: {"model": ApprovalsErrorBody},
    404: {"model": ApprovalsErrorBody},
}
_TRANSITION_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    202: {"model": TransitionOut, "description": "Recorded; waits for a countersign"},
    409: {
        "model": ApprovalsErrorBody,
        "description": "INVALID_TRANSITION, VERSION_CONFLICT, countersign",
    },
    422: {
        "model": ApprovalsErrorBody,
        "description": "Validation error, GUARD_FAILED or GUARD_ERROR",
    },
}


def _actor(request: Request, access: AccessPrincipal, principal: Principal) -> Actor:
    session = SessionFacts(
        aal=principal.aal, amr=tuple(principal.amr), authenticated_at=principal.authenticated_at
    )
    client = request.client
    return Actor(principal=access, session=session, ip_address=client.host if client else None)


async def actor(
    request: Request,
    access: Annotated[AccessPrincipal, Depends(current_principal)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> Actor:
    return _actor(request, access, principal)


CurrentActor = Annotated[Actor, Depends(actor)]


def _service(request: Request) -> TransitionService:
    policy: PolicyService = request.app.state.access_policy
    return TransitionService(policy)


def _instance_out(view: InstanceView) -> InstanceOut:
    row = view.instance
    return InstanceOut(
        id=row["id"],
        record_type=row["record_type"],
        record_id=row["record_id"],
        project_id=row["project_id"],
        definition_id=row["definition_id"],
        definition_key=view.definition.key,
        version=view.definition.version,
        current_state=row["current_state"],
        sync_version=row["sync_version"],
        pending_countersign=view.pending_countersign,
        available_transitions=[
            AvailableTransition(
                action=a.transition.action,
                to_state=a.transition.to_state,
                label_key=a.transition.label_key,
                critical=a.transition.critical,
                allowed=a.allowed,
                reason_key=a.reason_key,
            )
            for a in view.available
        ],
    )


def _decision_out(entry: dict[str, Any]) -> DecisionOut:
    """A decision for the API: everything but the client IP, which stays in the evidence."""
    return DecisionOut(
        id=entry["id"],
        seq=entry["seq"],
        from_state=entry["from_state"],
        to_state=entry["to_state"],
        action=entry["action"],
        actor_id=entry["actor_id"],
        on_behalf_of=entry["on_behalf_of"],
        comment=entry["comment"],
        auth_strength=entry["auth_strength"],
        status=entry["status"],
        countersigns_id=entry["countersigns_id"],
        assurance=AssuranceOut(
            level=entry["assurance_level"],
            method=entry["assurance_method"],
            authenticated_at=entry["authenticated_at"],
            device_id=entry["device_id"],
        ),
        guard_result=entry["guard_result"],
        prev_hash=entry["prev_hash"],
        entry_hash=entry["entry_hash"],
        created_at=entry["created_at"],
    )


# The access check reads route-level declarations, so authenticated() sits on the router.
instances_router = APIRouter(
    prefix="/approvals/instances", tags=["approvals"], dependencies=[Depends(authenticated())]
)


@instances_router.post(
    "",
    operation_id="approvals_start_instance",
    response_model=InstanceOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_ERRORS,
        422: {"model": ApprovalsErrorBody, "description": "NO_ACTIVE_DEFINITION"},
    },
)
async def start_instance(body: InstanceStart, request: Request, who: CurrentActor) -> InstanceOut:
    async with with_tenant(get_context()) as conn:
        view = await _service(request).start_for_client(
            conn, who, body.record_type, body.record_id, body.project_id
        )
    return _instance_out(view)


@instances_router.get(
    "/{instance_id}",
    operation_id="approvals_get_instance",
    response_model=InstanceOut,
    responses=_ERRORS,
)
async def get_instance(instance_id: UUID, request: Request, who: CurrentActor) -> InstanceOut:
    async with with_tenant(get_context()) as conn:
        view = await _service(request).describe(conn, who, instance_id)
    return _instance_out(view)


@instances_router.post(
    "/{instance_id}/transition",
    operation_id="approvals_transition",
    response_model=TransitionOut,
    responses=_TRANSITION_ERRORS,
)
async def transition(
    instance_id: UUID,
    body: TransitionRequest,
    request: Request,
    response: Response,
    who: CurrentActor,
) -> TransitionOut:
    async with with_tenant(get_context()) as conn:
        result = await _service(request).transition(
            conn,
            who,
            instance_id,
            body.action,
            comment=body.comment,
            expected_sync_version=body.expected_sync_version,
        )
    if not result.applied:
        response.status_code = status.HTTP_202_ACCEPTED
    return TransitionOut(
        instance=_instance_out(result.view), decision=_decision_out(result.decision)
    )


@instances_router.get(
    "/{instance_id}/history",
    operation_id="approvals_get_history",
    response_model=HistoryOut,
    responses=_ERRORS,
)
async def get_history(instance_id: UUID, request: Request, who: CurrentActor) -> HistoryOut:
    async with with_tenant(get_context()) as conn:
        history = await _service(request).history(conn, who, instance_id)
    broken = history.chain.broken_at_seq if isinstance(history.chain, ChainBroken) else None
    return HistoryOut(
        entries=[_decision_out(e) for e in history.entries],
        chain_valid=history.chain.ok,
        broken_at_seq=broken,
    )


router = APIRouter(dependencies=[Depends(require_active_tenant)])
router.include_router(instances_router)
# TESTING-13: the dev/test-only demo record type and its fixture switch (404 in production).
demo.install()
router.include_router(demo.router)
