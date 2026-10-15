"""Dead-letter queue API for ``/admin/platform/events/dead-letter`` (ARCH-07).

Mounted by ``aip.main`` under ``/api/v1`` *before* the event catalogue router, whose
``/{event_name}`` would otherwise match ``dead-letter``. Every endpoint needs
``platform.events.manage`` (platform operators). Rows come from ``SECURITY DEFINER`` functions that
read across tenants but never return a payload (migration ``202610151800``).

- ``GET /admin/platform/events/dead-letter`` — dead-lettered, undiscarded events, keyset-paged by
  id (``limit``, ``after``).
- ``POST .../dead-letter/{event_id}/retry`` — clear the dead letter so the dispatcher tries again
  from attempt 1; emits ``platform.outbox.retried``.
- ``POST .../dead-letter/{event_id}/discard`` with ``{"reason": "..."}`` (required, non-blank) —
  drop it for good; emits ``platform.outbox.discarded``.

Both actions return 404 for an event that is not (or no longer) in the dead-letter queue. The
audit events go to the operator's own tenant outbox, like ``platform.event.deprecated``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel
from sqlalchemy import text

from aip.platform.access import AccessPrincipal, requires
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant
from aip.platform.events.outbox import Aggregate, emit
from aip.platform.events.registry import PLATFORM_OUTBOX_DISCARDED, PLATFORM_OUTBOX_RETRIED

__all__ = ["create_router"]

EVENTS_MANAGE = Depends(requires("platform.events.manage"))
Operator = Annotated[AccessPrincipal, EVENTS_MANAGE]


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class DeadLetter(_Model):
    id: UUID
    tenant_id: UUID
    event_name: str
    event_version: int
    attempts: int
    last_error: str | None
    dead_lettered_at: datetime


class DeadLetterPage(_Model):
    items: list[DeadLetter]
    next_after: UUID | None


class DiscardRequest(_Model):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class DeadLetterAction(_Model):
    id: UUID
    event_name: str
    event_version: int
    action: str


def create_router() -> APIRouter:
    router = APIRouter(prefix="/admin/platform/events/dead-letter", tags=["platform"])

    @router.get("", response_model=DeadLetterPage, dependencies=[EVENTS_MANAGE])
    async def list_dead_letters(  # pyright: ignore[reportUnusedFunction]
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        after: Annotated[UUID | None, Query()] = None,
    ) -> DeadLetterPage:
        async with with_tenant(get_context()) as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, tenant_id, event_name, event_version, attempts, last_error,"
                        " dead_lettered_at FROM outbox_dead_letters(:lim, :after)"
                    ),
                    {"lim": limit, "after": after},
                )
            ).mappings()
            items = [DeadLetter.model_validate(dict(row)) for row in rows]
        next_after = items[-1].id if len(items) == limit else None
        return DeadLetterPage(items=items, next_after=next_after)

    @router.post("/{event_id}/retry", response_model=DeadLetterAction)
    async def retry_dead_letter(  # pyright: ignore[reportUnusedFunction]
        principal: Operator,
        event_id: Annotated[UUID, Path()],
    ) -> DeadLetterAction:
        async with with_tenant(get_context()) as conn:
            row = (
                await conn.execute(
                    text("SELECT event_name, event_version FROM outbox_retry(:id)"),
                    {"id": event_id},
                )
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="event is not in the dead-letter queue")
            await emit(
                conn,
                PLATFORM_OUTBOX_RETRIED,
                1,
                Aggregate("domain_event", event_id),
                {
                    "event_id": str(event_id),
                    "event_name": row.event_name,
                    "event_version": row.event_version,
                },
            )
        return DeadLetterAction(
            id=event_id,
            event_name=row.event_name,
            event_version=row.event_version,
            action="retried",
        )

    @router.post("/{event_id}/discard", response_model=DeadLetterAction)
    async def discard_dead_letter(  # pyright: ignore[reportUnusedFunction]
        principal: Operator,
        event_id: Annotated[UUID, Path()],
        body: DiscardRequest,
    ) -> DeadLetterAction:
        async with with_tenant(get_context()) as conn:
            row = (
                await conn.execute(
                    text("SELECT event_name, event_version FROM outbox_discard(:id, :reason, :by)"),
                    {"id": event_id, "reason": body.reason, "by": principal.actor_id},
                )
            ).first()
            if row is None:
                raise HTTPException(status_code=404, detail="event is not in the dead-letter queue")
            await emit(
                conn,
                PLATFORM_OUTBOX_DISCARDED,
                1,
                Aggregate("domain_event", event_id),
                {
                    "event_id": str(event_id),
                    "event_name": row.event_name,
                    "event_version": row.event_version,
                    "reason": body.reason,
                },
            )
        return DeadLetterAction(
            id=event_id,
            event_name=row.event_name,
            event_version=row.event_version,
            action="discarded",
        )

    return router
