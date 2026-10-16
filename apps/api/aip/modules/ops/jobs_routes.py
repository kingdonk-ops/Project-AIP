"""The jobs API (OPS-03), mounted under ``/api/v1``.

- ``GET /jobs/mine``: the caller's own jobs, newest first (any signed-in user).
- ``GET /admin/jobs``: every job in the tenant, filterable by status, type and requester
  (``ops.jobs.admin``).
- ``POST /jobs/{job_id}/cancel``: the requester or a jobs admin; 403 ``FORBIDDEN`` for anyone else,
  409 ``JOB_FINISHED`` once it has succeeded, failed or been cancelled.
- ``POST /jobs/{job_id}/retry``: queues a fresh copy of a failed job (409 ``JOB_NOT_FAILED``).

Another tenant's job is a 404 (RLS hides it). Every list item carries ``correlationId`` and
``error``, so a failure can be traced to its request.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from aip.modules.tenancy.api import require_active_tenant
from aip.platform.access import AccessPrincipal, PolicyService, authenticated, requires
from aip.platform.context import get_context
from aip.platform.db.errors import NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.http.errors import DomainError

from . import repository, service
from .jobs_access import JOBS_ADMIN
from .schemas import JobErrorBody, JobOut, JobPage, JobStatus

__all__ = ["router"]

Limit = Annotated[int, Query(ge=1, le=100)]
After = Annotated[UUID | None, Query(description="The last id of the previous page.")]
Statuses = Annotated[list[JobStatus], Query(alias="status")]

_ACTION_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"description": "Not the requester and not a jobs admin."},
    404: {"model": JobErrorBody, "description": "No such job in this tenant."},
    409: {"model": JobErrorBody, "description": "The job's status does not allow this."},
}

router = APIRouter(tags=["jobs"], dependencies=[Depends(require_active_tenant)])


def _page(rows: list[Any], limit: int) -> JobPage:
    items = [JobOut.model_validate(row) for row in rows]
    return JobPage(items=items, next_cursor=items[-1].id if len(items) == limit else None)


@router.get("/jobs/mine", operation_id="jobs_list_mine", response_model=JobPage)
async def list_my_jobs(
    principal: Annotated[AccessPrincipal, Depends(authenticated())],
    limit: Limit = 20,
    after: After = None,
    status_: Statuses = [],  # noqa: B006 - FastAPI copies it
) -> JobPage:
    if principal.actor_id is None:
        return JobPage(items=[], next_cursor=None)
    async with with_tenant(get_context()) as conn:
        rows = await repository.list_jobs(
            conn,
            requested_by=principal.actor_id,
            statuses=[s.value for s in status_],
            after=after,
            limit=limit,
        )
    return _page(rows, limit)


@router.get(
    "/admin/jobs",
    operation_id="jobs_admin_list",
    response_model=JobPage,
    dependencies=[Depends(requires(JOBS_ADMIN))],
)
async def list_tenant_jobs(
    limit: Limit = 50,
    after: After = None,
    status_: Statuses = [],  # noqa: B006 - FastAPI copies it
    job_type: Annotated[str | None, Query(alias="jobType", min_length=1, max_length=100)] = None,
    requested_by: Annotated[UUID | None, Query(alias="requestedBy")] = None,
) -> JobPage:
    async with with_tenant(get_context()) as conn:
        rows = await repository.list_jobs(
            conn,
            requested_by=requested_by,
            statuses=[s.value for s in status_],
            job_type=job_type,
            after=after,
            limit=limit,
        )
    return _page(rows, limit)


async def _is_admin(request: Request, principal: AccessPrincipal) -> bool:
    policy: PolicyService = request.app.state.access_policy
    return (await policy.can(principal, JOBS_ADMIN)).allowed


async def _act(request: Request, principal: AccessPrincipal, job_id: UUID, action: str) -> JobOut:
    is_admin = await _is_admin(request, principal)
    act = service.cancel_job if action == "cancel" else service.retry_job
    try:
        async with with_tenant(get_context()) as conn:
            job = await act(conn, job_id, actor_id=principal.actor_id, is_admin=is_admin)
    except service.JobNotFound as exc:
        raise NotFoundError(str(exc)) from None
    except service.JobForbidden:
        raise DomainError(status.HTTP_403_FORBIDDEN, "FORBIDDEN") from None
    except service.JobStateConflict as exc:
        raise DomainError(status.HTTP_409_CONFLICT, exc.code, status=exc.status.value) from None
    return JobOut.model_validate(job)


@router.post(
    "/jobs/{job_id}/cancel",
    operation_id="jobs_cancel",
    response_model=JobOut,
    responses=_ACTION_ERRORS,
)
async def cancel_job(
    job_id: UUID,
    request: Request,
    principal: Annotated[AccessPrincipal, Depends(authenticated())],
) -> JobOut:
    return await _act(request, principal, job_id, "cancel")


@router.post(
    "/jobs/{job_id}/retry",
    operation_id="jobs_retry",
    response_model=JobOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ACTION_ERRORS,
)
async def retry_job(
    job_id: UUID,
    request: Request,
    principal: Annotated[AccessPrincipal, Depends(authenticated())],
) -> JobOut:
    return await _act(request, principal, job_id, "retry")
