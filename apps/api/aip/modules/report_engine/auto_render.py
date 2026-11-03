"""Auto-render on approval (REPORTS-03): ``inspection.state_changed`` v1 queues the reports.

``on_inspection_state_changed(conn, event)`` runs in the event's dispatch transaction (ADR 0030),
so each snapshot is taken in the same transaction as the approval's event delivery:

(a) ``repository.list_auto_render_templates(record_type="inspection", state=payload["to"])``: the
    latest published version per ``(key, variant)`` whose ``autoRender.onStates`` holds the new
    state. None: nothing to do.
(b) For each, inside a savepoint, ``RenderService.request_render`` with the idempotency key
    ``auto:<eventId>:<key>:<variant>``, ``trigger_event_id`` = the event, ``requested_by`` = its
    actor and ``context = {approvedAt: occurred_at, approvedBy: actor}`` for the provider. A
    redelivered event finds its render jobs by key and creates nothing.
(c) A report request error (a ``DomainError`` such as ``TEMPLATE_NOT_FOUND``, ``RECORD_NOT_FOUND``
    or ``SNAPSHOT_TOO_LARGE``) rolls back only that savepoint and is logged with the event id,
    template key, variant and error code, never record data. The handler does not raise, so the
    event's other subscribers still commit. Any other exception is raised, so the dispatcher
    retries the event.

No policy check: the transition service authorised the approval; this is a system action.
Manual renders (``POST /api/v1/reports/renders``) keep their ``report.create`` and view checks.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Final, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine import repository as repo
from aip.modules.report_engine.providers import RecordNotFound
from aip.modules.report_engine.providers.inspection import INSPECTION_RECORD_TYPE
from aip.platform.events.subscribers import DomainEvent
from aip.platform.http import DomainError

__all__ = ["AutoRender", "Renderer", "TemplateLister", "auto_render", "idempotency_key"]

logger = logging.getLogger(__name__)

_RECORD_NOT_FOUND: Final = "RECORD_NOT_FOUND"


class Renderer(Protocol):
    """The part of ``RenderService`` auto-render uses (a fake in the unit tests)."""

    async def request_render(
        self,
        conn: AsyncConnection,
        *,
        template_key: str,
        record_type: str,
        record_id: UUID,
        variant: str,
        requested_by: UUID | None,
        idempotency_key: str | None = None,
        trigger_event_id: UUID | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any: ...


TemplateLister = Callable[..., Awaitable[list[dict[str, Any]]]]


def idempotency_key(event_id: UUID, key: str, variant: str) -> str:
    return f"auto:{event_id}:{key}:{variant}"


class AutoRender:
    """Queues the auto-render templates of a state change; dependencies are injectable."""

    def __init__(
        self,
        renderer: Renderer | None = None,
        list_templates: TemplateLister = repo.list_auto_render_templates,
    ) -> None:
        self._renderer = renderer
        self._list_templates = list_templates

    @property
    def renderer(self) -> Renderer:
        if self._renderer is None:
            # Imported here: render_service registers the providers, which import this package.
            from aip.modules.report_engine.render_service import RenderService

            self._renderer = RenderService()
        return self._renderer

    async def on_inspection_state_changed(self, conn: AsyncConnection, event: DomainEvent) -> None:
        state = str(event.payload.get("to", ""))
        templates = await self._list_templates(
            conn, record_type=INSPECTION_RECORD_TYPE, state=state
        )
        if not templates:
            return
        inspection_id = UUID(str(event.payload["inspectionId"]))
        context = {"approvedAt": event.occurred_at, "approvedBy": event.actor_id}
        for template in templates:
            key, variant = str(template["key"]), str(template["variant"])
            code: str | None = None
            try:
                async with conn.begin_nested():
                    await self.renderer.request_render(
                        conn,
                        template_key=key,
                        record_type=INSPECTION_RECORD_TYPE,
                        record_id=inspection_id,
                        variant=variant,
                        requested_by=event.actor_id,
                        idempotency_key=idempotency_key(event.id, key, variant),
                        trigger_event_id=event.id,
                        context=context,
                    )
            except DomainError as exc:
                code = exc.code
            except RecordNotFound:  # a pinned file vanished while the snapshot was built
                code = _RECORD_NOT_FOUND
            if code is not None:
                logger.warning(
                    "auto-render skipped: event %s template %s/%s error %s",
                    event.id,
                    key,
                    variant,
                    code,
                )


auto_render = AutoRender()
