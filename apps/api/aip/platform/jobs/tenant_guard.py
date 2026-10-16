"""Tenant guard for deferring jobs (OPS-03; carried forward from TENANCY-02, ADR 0003).

``TenantJobPayload`` is the queue-row payload of every tenant job: a validated ``TenantId`` plus the
request identity ``tenant_job`` rebuilds the context from. ``defer_for_tenant`` refuses to enqueue a
tenant job without one, or for a tenant other than the one the caller's ``with_tenant`` connection
is bound to, so a job can never be queued for another tenant by mistake. ``tenant_task`` is
``tenant_job`` that also validates the incoming payload before the handler runs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.jobs.app import defer_in_transaction
from aip.platform.jobs.context import TenantMismatchError, tenant_job
from aip.platform.tenant_keys import TenantId, TenantKeyError

__all__ = ["TenantJobPayload", "defer_for_tenant", "tenant_task"]

_CURRENT_TENANT = text("SELECT NULLIF(current_setting('app.tenant_id', true), '')")


class TenantJobPayload(BaseModel):
    """What a tenant job's queue row carries; extra keys are the job's own arguments."""

    model_config = ConfigDict(extra="allow", frozen=True)

    tenant_id: str
    actor_id: str | None = None
    project_id: str | None = None
    request_id: str | None = None

    @field_validator("tenant_id", mode="before")
    @classmethod
    def _tenant(cls, value: object) -> str:
        try:
            return str(TenantId(value))
        except TenantKeyError as exc:
            raise ValueError(str(exc)) from None

    @field_validator("actor_id", "project_id", mode="before")
    @classmethod
    def _uuid_or_none(cls, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value if isinstance(value, UUID) else UUID(str(value)))


async def defer_for_tenant(
    conn: AsyncConnection,
    *,
    task_name: str,
    queue: str,
    payload: TenantJobPayload,
    lock: str | None = None,
) -> int:
    """Defer a tenant job on ``conn``, only for the tenant ``conn`` is bound to."""
    bound = (await conn.execute(_CURRENT_TENANT)).scalar_one_or_none()
    if bound is None:
        raise TenantMismatchError("defer_for_tenant needs a with_tenant connection")
    if str(TenantId(bound)) != payload.tenant_id:
        raise TenantMismatchError("job payload tenant_id differs from the connection's tenant")
    args = payload.model_dump(exclude_none=True)
    return await defer_in_transaction(conn, task_name=task_name, queue=queue, args=args, lock=lock)


def tenant_task[R](fn: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
    """``tenant_job`` plus payload validation: a bad ``tenant_id`` fails before the handler."""
    wrapped = tenant_job(fn)

    async def run(*args: Any, **kwargs: Any) -> R:
        TenantJobPayload.model_validate(kwargs)
        return await wrapped(*args, **kwargs)

    run.__name__ = getattr(fn, "__name__", "tenant_task")
    run.__doc__ = fn.__doc__
    return run
