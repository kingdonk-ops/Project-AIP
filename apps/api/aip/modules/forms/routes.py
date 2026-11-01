"""HTTP routes for forms (FORMS-01), mounted under ``/api/v1/forms``.

Every route declares its permission with ``requires(...)`` (deny by default, ACCESS-01) and needs
an active tenant. Reading needs ``form.view``; uploading and editing drafts need ``form.manage``;
publishing needs ``form.publish``. Explicit ``operation_id``s keep the generated client's hook
names stable, and the ``422`` description is pinned so the OpenAPI schema does not drift across
Python versions (FastAPI otherwise fills it from ``HTTPStatus(422).phrase``, renamed in 3.13).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from aip.modules.forms.schemas import (
    AnswerEvaluationOut,
    EvaluateBody,
    FormErrorBody,
    LintBody,
    LintResult,
    PublishBody,
    RevisionCreate,
    RevisionOut,
    RevisionReplace,
    TemplateCreate,
    TemplateDetail,
    TemplatePage,
    TemplateRecord,
    TemplateUpdate,
    UploadResult,
)
from aip.modules.forms.service import FormsService
from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import requires

__all__ = ["router"]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": FormErrorBody}}
_CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": FormErrorBody}}
_INVALID: dict[int | str, dict[str, Any]] = {
    422: {"model": FormErrorBody, "description": "Unprocessable Entity"}
}

Kind = Annotated[str | None, Query(pattern=r"^(inspection|itp|rfi|permit|test_report)$")]
Status = Annotated[str | None, Query(alias="status", pattern=r"^(draft|active|retired)$")]
Search = Annotated[str | None, Query(min_length=1, max_length=100)]
Limit = Annotated[int, Query(ge=1, le=200)]

router = APIRouter(prefix="/forms", tags=["forms"], dependencies=[Depends(require_active_tenant)])


# --- templates --------------------------------------------------------------------------------


@router.get(
    "/templates",
    operation_id="forms_templates_list",
    response_model=TemplatePage,
    dependencies=[Depends(requires("form.view"))],
)
async def list_templates(
    kind: Kind = None, status_: Status = None, q: Search = None, limit: Limit = 50
) -> TemplatePage:
    return await FormsService().list_templates(kind=kind, status=status_, q=q, limit=limit)


@router.post(
    "/templates",
    operation_id="forms_templates_create",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
    responses={**_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("form.manage"))],
)
async def create_template(body: TemplateCreate) -> UploadResult:
    return await FormsService().upload_template(body)


@router.get(
    "/templates/{template_id}",
    operation_id="forms_templates_get",
    response_model=TemplateDetail,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("form.view"))],
)
async def get_template(template_id: UUID) -> TemplateDetail:
    return await FormsService().get_template(template_id)


@router.patch(
    "/templates/{template_id}",
    operation_id="forms_templates_update",
    response_model=TemplateRecord,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("form.manage"))],
)
async def update_template(template_id: UUID, body: TemplateUpdate) -> TemplateRecord:
    return await FormsService().update_template(template_id, body)


@router.post(
    "/templates/{template_id}/revisions",
    operation_id="forms_templates_add_revision",
    response_model=RevisionOut,
    status_code=status.HTTP_201_CREATED,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("form.manage"))],
)
async def create_revision(template_id: UUID, body: RevisionCreate) -> RevisionOut:
    return await FormsService().create_draft(template_id, body)


# --- revisions --------------------------------------------------------------------------------


@router.get(
    "/revisions/{revision_id}",
    operation_id="forms_revisions_get",
    response_model=RevisionOut,
    responses=_NOT_FOUND,
    dependencies=[Depends(requires("form.view"))],
)
async def get_revision(revision_id: UUID) -> RevisionOut:
    return await FormsService().get_revision(revision_id)


@router.put(
    "/revisions/{revision_id}",
    operation_id="forms_revisions_replace",
    response_model=RevisionOut,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("form.manage"))],
)
async def replace_revision(revision_id: UUID, body: RevisionReplace) -> RevisionOut:
    return await FormsService().replace_draft(revision_id, body)


@router.delete(
    "/revisions/{revision_id}",
    operation_id="forms_revisions_discard",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**_NOT_FOUND, **_CONFLICT},
    dependencies=[Depends(requires("form.manage"))],
)
async def discard_revision(revision_id: UUID) -> Response:
    await FormsService().discard_draft(revision_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/revisions/{revision_id}/publish",
    operation_id="forms_revisions_publish",
    response_model=UploadResult,
    responses={**_NOT_FOUND, **_CONFLICT, **_INVALID},
    dependencies=[Depends(requires("form.publish"))],
)
async def publish_revision(revision_id: UUID, body: PublishBody | None = None) -> UploadResult:
    expected = body.expected_sync_version if body is not None else None
    return await FormsService().publish(revision_id, expected)


@router.post(
    "/revisions/{revision_id}/evaluate",
    operation_id="forms_revisions_evaluate",
    response_model=AnswerEvaluationOut,
    responses={**_NOT_FOUND, **_INVALID},
    dependencies=[Depends(requires("form.view"))],
)
async def evaluate_revision(revision_id: UUID, body: EvaluateBody) -> dict[str, Any]:
    return await FormsService().evaluate(revision_id, body)


# --- lint -------------------------------------------------------------------------------------


@router.post(
    "/lint",
    operation_id="forms_lint",
    response_model=LintResult,
    dependencies=[Depends(requires("form.manage"))],
)
async def lint_template(body: LintBody) -> LintResult:
    return await FormsService().lint(body.schema_)
