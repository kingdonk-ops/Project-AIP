"""HTTP routes for approvals (APPROVALS-02), mounted under ``/api/v1/approvals``.

- ``POST /instances`` starts (or returns) a record's workflow (``approvals.start``);
- ``GET /instances/{id}`` returns its state, pinned version and ``availableTransitions`` for the
  caller (``approvals.view``);
- ``POST /instances/{id}/transition`` takes an action (``approvals.view`` plus the transition's own
  ``requiredPermission``); 200 when it took effect, 202 when it waits for a countersign;
- ``GET /instances/{id}/history`` returns the decisions and ``chainValid`` (``approvals.view``);
- ``GET /presets`` lists the ``config/workflows`` presets (``approvals.view``) and
  ``POST /definitions/from-preset`` installs one, tenant-wide or for a project, idempotently
  (``approvals.design``; 404 ``PRESET_NOT_FOUND``) (APPROVALS-05);
- approval routes (APPROVALS-04): ``POST``/``GET /route-templates`` (``approvals.design``),
  ``POST /instances/{id}/route`` starts one (``approvals.start``), ``POST /instances/{id}/decide``
  decides a step (``approvals.approve`` and eligibility) and ``GET /instances/{id}/steps``
  returns the latest round (``approvals.view``).

Every route is ``authenticated()`` and the service checks each permission against the instance's
project, which is known only once the instance is loaded (deny by default either way). Another
tenant's instance is 404. Bodies forbid unknown keys (422), so a client cannot send a guard
outcome. Explicit ``operation_id``s keep the generated client's hook names stable.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from aip.modules.approvals.decision_chain import ChainBroken
from aip.modules.approvals.presets import list_presets
from aip.modules.approvals.routes_engine.service import RoutesService, RouteTemplate, RouteView
from aip.modules.approvals.schemas import (
    ApprovalsErrorBody,
    AssuranceOut,
    AvailableTransition,
    DecisionOut,
    DefinitionOut,
    HistoryOut,
    InstanceOut,
    InstanceStart,
    PresetInstall,
    PresetOut,
    RouteOut,
    RouteStart,
    RouteStepOut,
    RouteTemplateCreate,
    RouteTemplateOut,
    StepDecisionOut,
    StepDecisionRequest,
    TransitionOut,
    TransitionRequest,
)
from aip.modules.approvals.service import DefinitionsService
from aip.modules.approvals.transition import Actor, InstanceView, TransitionService
from aip.modules.identity.api import Principal, SessionFacts, get_principal
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import (
    AccessPrincipal,
    PolicyService,
    authenticated,
    current_principal,
    requires,
)
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant
from aip.platform.http import DomainError

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
        "description": "Validation error, COMMENT_REQUIRED, GUARD_FAILED or GUARD_ERROR",
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


def _routes(request: Request) -> RoutesService:
    policy: PolicyService = request.app.state.access_policy
    return RoutesService(policy)


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
                requires_comment=a.transition.requires_comment,
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


def _step_out(step: dict[str, Any]) -> RouteStepOut:
    return RouteStepOut(
        id=step["id"],
        step_order=step["step_order"],
        mode=step["mode"],
        approver_type=step["approver_type"],
        approver_ref=step["approver_ref"],
        due_hours=step["due_hours"],
        status=step["status"],
        due_at=step["due_at"],
        decided_by=step["decided_by"],
        decided_at=step["decided_at"],
    )


def _route_out(route: RouteView) -> RouteOut:
    row = route.view.instance
    return RouteOut(
        instance=_instance_out(route.view),
        route_template_id=row["route_template_id"],
        route_round=row["route_round"],
        current_step_id=row["current_step_id"],
        steps=[_step_out(s) for s in route.steps],
    )


def _template_out(found: RouteTemplate) -> RouteTemplateOut:
    t = found.template
    return RouteTemplateOut(
        id=t["id"],
        name=t["name"],
        record_type=t["record_type"],
        version=t["version"],
        on_approved_action=t["on_approved_action"],
        on_rejected_action=t["on_rejected_action"],
        allow_self_approval=t["allow_self_approval"],
        steps=[_step_out(s) for s in found.steps],
        created_at=t["created_at"],
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


@instances_router.post(
    "/{instance_id}/route",
    operation_id="approvals_start_route",
    response_model=RouteOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        **_ERRORS,
        409: {"model": ApprovalsErrorBody, "description": "ROUTE_ACTIVE, COUNTERSIGN_PENDING"},
        422: {
            "model": ApprovalsErrorBody,
            "description": "Validation error, ROUTE_TEMPLATE_MISMATCH or ROUTE_ACTION_INVALID",
        },
    },
)
async def start_route(
    instance_id: UUID, body: RouteStart, request: Request, who: CurrentActor
) -> RouteOut:
    async with with_tenant(get_context()) as conn:
        route = await _routes(request).start_route(conn, who, instance_id, body.route_template_id)
    return _route_out(route)


@instances_router.post(
    "/{instance_id}/decide",
    operation_id="approvals_decide_step",
    response_model=StepDecisionOut,
    responses={
        **_ERRORS,
        409: {
            "model": ApprovalsErrorBody,
            "description": "STEP_NOT_PENDING, INVALID_TRANSITION, COUNTERSIGN_PENDING",
        },
        422: {
            "model": ApprovalsErrorBody,
            "description": "Validation error, COMMENT_REQUIRED, GUARD_FAILED or GUARD_ERROR",
        },
    },
)
async def decide_step(
    instance_id: UUID, body: StepDecisionRequest, request: Request, who: CurrentActor
) -> StepDecisionOut:
    async with with_tenant(get_context()) as conn:
        result = await _routes(request).decide(
            conn, who, instance_id, body.step_id, body.decision, body.comment
        )
    return StepDecisionOut(
        route=_route_out(result.route),
        decision=_decision_out(result.decision),
        outcome=result.outcome,
    )


@instances_router.get(
    "/{instance_id}/steps",
    operation_id="approvals_get_steps",
    response_model=RouteOut,
    responses=_ERRORS,
)
async def get_steps(instance_id: UUID, request: Request, who: CurrentActor) -> RouteOut:
    async with with_tenant(get_context()) as conn:
        route = await _routes(request).route(conn, who, instance_id)
    return _route_out(route)


templates_router = APIRouter(
    prefix="/approvals/route-templates",
    tags=["approvals"],
    dependencies=[Depends(requires("approvals.design"))],
)


@templates_router.post(
    "",
    operation_id="approvals_create_route_template",
    response_model=RouteTemplateOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {
            "model": ApprovalsErrorBody,
            "description": "Validation error, ROUTE_SHAPE_INVALID or UNKNOWN_APPROVER",
        }
    },
)
async def create_route_template(
    body: RouteTemplateCreate, request: Request, who: CurrentActor
) -> RouteTemplateOut:
    async with with_tenant(get_context()) as conn:
        created = await _routes(request).create_template(conn, who, body)
    return _template_out(created)


@templates_router.get(
    "",
    operation_id="approvals_list_route_templates",
    response_model=list[RouteTemplateOut],
)
async def list_route_templates(request: Request, who: CurrentActor) -> list[RouteTemplateOut]:
    async with with_tenant(get_context()) as conn:
        found = await _routes(request).list_templates(conn, who)
    return [_template_out(t) for t in found]


presets_router = APIRouter(prefix="/approvals", tags=["approvals"])


@presets_router.get(
    "/presets",
    operation_id="approvals_list_presets",
    response_model=list[PresetOut],
    dependencies=[Depends(requires("approvals.view"))],
)
async def get_presets() -> list[PresetOut]:
    return [
        PresetOut(
            key=p.key,
            record_type=p.record_type,
            initial=p.spec["initial"],
            states=[s["code"] for s in p.spec["states"]],
            actions=list(dict.fromkeys(t["action"] for t in p.spec["transitions"])),
        )
        for p in list_presets()
    ]


@presets_router.post(
    "/definitions/from-preset",
    operation_id="approvals_install_preset",
    response_model=DefinitionOut,
    responses={404: {"model": ApprovalsErrorBody, "description": "PRESET_NOT_FOUND"}},
    dependencies=[Depends(requires("approvals.design"))],
)
async def install_preset(body: PresetInstall) -> DefinitionOut:
    if all(p.key != body.preset_key for p in list_presets()):
        raise DomainError(404, "PRESET_NOT_FOUND")
    async with with_tenant(get_context()) as conn:
        definition = await DefinitionsService().install_preset(
            conn, body.preset_key, project_id=body.project_id
        )
    return DefinitionOut(
        id=definition.id,
        key=definition.key,
        record_type=definition.record_type,
        project_id=definition.project_id,
        version=definition.version,
        status=definition.status,
    )


router = APIRouter(dependencies=[Depends(require_active_tenant)])
router.include_router(instances_router)
router.include_router(presets_router)
router.include_router(templates_router)
