"""HTTP routes for inspections (INSPECTIONS-01), mounted under ``/api/v1/inspections``.

- ``POST /inspections`` creates a ``draft`` inspection (``inspection.create``): 201, or 200 for an
  idempotent replay of the same ``clientGeneratedId``. ``source`` is always ``manual`` here;
  ``source``/``sourceRefId`` are not accepted from clients (422).
- ``GET /inspections`` lists them, filtered to projects the caller may view (``inspection.view``).
- ``GET /inspections/{id}`` returns the record plus its workflow: ``currentState``,
  ``pendingCountersign`` and ``availableTransitions`` (``inspection.view``).
- ``POST /inspections/{id}/transition`` takes a lifecycle action through the approvals transition
  service (the transition's ``requiredPermission``): 200 when applied, 202 when it waits for a
  countersign; approvals' errors pass through (409, 403, 401 ``STEP_UP_REQUIRED``, 422).
- ``GET /inspections/{id}/history`` returns the decisions and ``chainValid`` (``inspection.view``).
- ``POST /inspections/{id}/reinspect`` creates the re-inspection of a performed one (201).
- ``POST /inspections/{id}/responses`` stores answers (``inspection.respond``; in supervisor review
  also ``approvals.inspection.review``): 200 with one result per answer, ``created: false`` for a
  ``clientId`` already stored. 409 ``INSPECTION_NOT_EDITABLE`` outside the editable states; 422
  ``DUPLICATE_ANSWER``, ``UNKNOWN_FIELD``, ``FIELD_NOT_VISIBLE`` or ``ANSWER_INVALID`` with
  ``errors: [{path, code}]``, and then nothing is written (INSPECTIONS-02).
- ``GET /inspections/{id}/responses`` returns the current answers and their evaluation, and
  ``GET /inspections/{id}/responses/{fieldKey}/history`` every answer to one field, oldest first
  (``inspection.view``).

Every route is ``authenticated()`` with an active tenant, and the service checks each permission
against the inspection's project (ADR 0035 §6), deny by default. Another tenant's id is 404 before
any permission check. Explicit ``operation_id``s keep the generated client's hook names stable.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from aip.modules.approvals.api import Actor, InstanceView
from aip.modules.identity.api import Principal, SessionFacts, get_principal
from aip.modules.inspections import repository as repo
from aip.modules.inspections.responses import ResponseService
from aip.modules.inspections.schemas import (
    FIELD_KEY_PATTERN,
    CurrentResponses,
    InspectionAvailableTransition,
    InspectionCreate,
    InspectionDecision,
    InspectionDetail,
    InspectionErrorBody,
    InspectionHistory,
    InspectionKind,
    InspectionOut,
    InspectionPage,
    InspectionTransitionOut,
    ResponseHistory,
    ResponsesIn,
    ResponsesOut,
    TransitionBody,
)
from aip.modules.inspections.service import InspectionService, NewInspection
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, PolicyService, authenticated, current_principal
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant

__all__ = ["router"]

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": InspectionErrorBody, "description": "Not signed in, or STEP_UP_REQUIRED"},
    403: {"model": InspectionErrorBody},
    404: {"model": InspectionErrorBody},
}
_CREATE_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    200: {"model": InspectionOut, "description": "An idempotent replay of the same create"},
    422: {
        "model": InspectionErrorBody,
        "description": "Validation error, TEMPLATE_NOT_PUBLISHED, REVISION_MISMATCH or "
        "NO_INSPECTION_WORKFLOW",
    },
}
_TRANSITION_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    202: {"model": InspectionTransitionOut, "description": "Recorded; waits for a countersign"},
    409: {
        "model": InspectionErrorBody,
        "description": "INVALID_TRANSITION, VERSION_CONFLICT, countersign",
    },
    422: {
        "model": InspectionErrorBody,
        "description": "Validation error, COMMENT_REQUIRED, GUARD_FAILED or GUARD_ERROR",
    },
}

_RESPOND_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    409: {"model": InspectionErrorBody, "description": "INSPECTION_NOT_EDITABLE"},
    422: {
        "model": InspectionErrorBody,
        "description": "Validation error, DUPLICATE_ANSWER, UNKNOWN_FIELD, FIELD_NOT_VISIBLE or "
        "ANSWER_INVALID",
    },
}

Limit = Annotated[int, Query(ge=1, le=200)]
FieldKeyPath = Annotated[str, Path(alias="fieldKey", pattern=FIELD_KEY_PATTERN)]
Cursor = Annotated[str | None, Query(max_length=1024)]


async def actor(
    request: Request,
    access: Annotated[AccessPrincipal, Depends(current_principal)],
    principal: Annotated[Principal, Depends(get_principal)],
) -> Actor:
    session = SessionFacts(
        aal=principal.aal, amr=tuple(principal.amr), authenticated_at=principal.authenticated_at
    )
    client = request.client
    return Actor(principal=access, session=session, ip_address=client.host if client else None)


CurrentActor = Annotated[Actor, Depends(actor)]


def _service(request: Request) -> InspectionService:
    policy: PolicyService = request.app.state.access_policy
    return InspectionService(policy)


def _responses(request: Request) -> ResponseService:
    policy: PolicyService = request.app.state.access_policy
    return ResponseService(policy)


def _detail(row: dict[str, Any], view: InstanceView) -> InspectionDetail:
    instance = view.instance
    return InspectionDetail.model_validate(
        {
            **row,
            "current_state": instance["current_state"],
            "instance_sync_version": instance["sync_version"],
            "pending_countersign": view.pending_countersign,
            "available_transitions": [
                InspectionAvailableTransition(
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
        }
    )


inspections_router = APIRouter(
    prefix="/inspections", tags=["inspections"], dependencies=[Depends(authenticated())]
)


@inspections_router.post(
    "",
    operation_id="inspections_create",
    response_model=InspectionOut,
    status_code=status.HTTP_201_CREATED,
    responses=_CREATE_ERRORS,
)
async def create_inspection(
    body: InspectionCreate, request: Request, response: Response, who: CurrentActor
) -> InspectionOut:
    data = NewInspection(
        asset_id=body.asset_id,
        template_id=body.template_id,
        kind=body.kind,
        project_id=body.project_id,
        template_revision_id=body.template_revision_id,
        client_generated_id=body.client_generated_id,
    )
    async with with_tenant(get_context()) as conn:
        row, created = await _service(request).create(conn, who, data)
    if not created:  # an idempotent replay returns the first row with 200
        response.status_code = status.HTTP_200_OK
    return InspectionOut.model_validate(row)


@inspections_router.get(
    "",
    operation_id="inspections_list",
    response_model=InspectionPage,
    responses={**_ERRORS, 422: {"model": InspectionErrorBody, "description": "INVALID_CURSOR"}},
)
async def list_inspections(
    request: Request,
    who: CurrentActor,
    asset_id: Annotated[UUID | None, Query(alias="assetId")] = None,
    project_id: Annotated[UUID | None, Query(alias="projectId")] = None,
    state: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    kind: InspectionKind | None = None,
    cursor: Cursor = None,
    limit: Limit = 50,
) -> InspectionPage:
    filters = repo.Filters(asset_id=asset_id, project_id=project_id, state=state, kind=kind)
    async with with_tenant(get_context()) as conn:
        page = await _service(request).list(conn, who, filters, limit=limit, cursor=cursor)
    return InspectionPage(
        items=[InspectionOut.model_validate(r) for r in page.items], next_cursor=page.next_cursor
    )


@inspections_router.get(
    "/{inspection_id}",
    operation_id="inspections_get",
    response_model=InspectionDetail,
    responses=_ERRORS,
)
async def get_inspection(
    inspection_id: UUID, request: Request, who: CurrentActor
) -> InspectionDetail:
    async with with_tenant(get_context()) as conn:
        row, view = await _service(request).describe(conn, who, inspection_id)
    return _detail(row, view)


@inspections_router.post(
    "/{inspection_id}/transition",
    operation_id="inspections_transition",
    response_model=InspectionTransitionOut,
    responses=_TRANSITION_ERRORS,
)
async def transition(
    inspection_id: UUID,
    body: TransitionBody,
    request: Request,
    response: Response,
    who: CurrentActor,
) -> InspectionTransitionOut:
    async with with_tenant(get_context()) as conn:
        row, result = await _service(request).transition(
            conn,
            who,
            inspection_id,
            body.action,
            comment=body.comment,
            expected_sync_version=body.expected_sync_version,
        )
    if not result.applied:
        response.status_code = status.HTTP_202_ACCEPTED
    return InspectionTransitionOut(
        inspection=_detail(row, result.view),
        decision=InspectionDecision.model_validate(result.decision),
    )


@inspections_router.get(
    "/{inspection_id}/history",
    operation_id="inspections_history",
    response_model=InspectionHistory,
    responses=_ERRORS,
)
async def get_history(
    inspection_id: UUID, request: Request, who: CurrentActor
) -> InspectionHistory:
    async with with_tenant(get_context()) as conn:
        history = await _service(request).history(conn, who, inspection_id)
    return InspectionHistory(
        entries=[InspectionDecision.model_validate(e) for e in history.entries],
        chain_valid=history.chain.ok,
        broken_at_seq=getattr(history.chain, "broken_at_seq", None),
    )


@inspections_router.post(
    "/{inspection_id}/reinspect",
    operation_id="inspections_reinspect",
    response_model=InspectionOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        **{code: spec for code, spec in _CREATE_ERRORS.items() if code != 200},
        409: {"model": InspectionErrorBody, "description": "NOT_COMPLETED"},
    },
)
async def reinspect(inspection_id: UUID, request: Request, who: CurrentActor) -> InspectionOut:
    async with with_tenant(get_context()) as conn:
        row = await _service(request).reinspect(conn, who, inspection_id)
    return InspectionOut.model_validate(row)


@inspections_router.post(
    "/{inspection_id}/responses",
    operation_id="inspections_respond",
    response_model=ResponsesOut,
    responses=_RESPOND_ERRORS,
)
async def respond(
    inspection_id: UUID, body: ResponsesIn, request: Request, who: CurrentActor
) -> ResponsesOut:
    async with with_tenant(get_context()) as conn:
        results = await _responses(request).submit(conn, who, inspection_id, body.answers)
    return ResponsesOut(results=results)


@inspections_router.get(
    "/{inspection_id}/responses",
    operation_id="inspections_responses",
    response_model=CurrentResponses,
    responses=_ERRORS,
)
async def get_responses(
    inspection_id: UUID, request: Request, who: CurrentActor
) -> CurrentResponses:
    async with with_tenant(get_context()) as conn:
        return await _responses(request).current(conn, who, inspection_id)


@inspections_router.get(
    "/{inspection_id}/responses/{fieldKey}/history",
    operation_id="inspections_response_history",
    response_model=ResponseHistory,
    responses=_ERRORS,
)
async def get_response_history(
    inspection_id: UUID, field_key: FieldKeyPath, request: Request, who: CurrentActor
) -> ResponseHistory:
    async with with_tenant(get_context()) as conn:
        entries = await _responses(request).history(conn, who, inspection_id, field_key)
    return ResponseHistory(entries=entries)


router = APIRouter(dependencies=[Depends(require_active_tenant)])
router.include_router(inspections_router)
