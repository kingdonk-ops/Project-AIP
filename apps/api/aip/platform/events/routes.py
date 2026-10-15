"""Event-catalogue API for the ``/admin/platform/events`` pages (ARCH-06).

Mounted by ``aip.main`` under ``/api/v1`` (outside the module registry, like ``/platform/modules``),
so it is always present. Every endpoint needs ``platform.events.manage`` through the policy service
(platform operators only; ADR 0017/0020: operators have no standing access to tenant data, and the
catalogue carries none — only event metadata and cross-tenant aggregate counts).

- ``GET /admin/platform/events`` — the catalogue, filterable by ``module``, ``status`` and
  ``version``; each row carries the owning module, status, subscribers, ``published_24h`` and
  ``failed_24h``.
- ``GET /admin/platform/events/{event_name}`` — every version's JSON Schema and subscribers.
- ``POST /admin/platform/events/{event_name}/versions/{version}/deprecate`` — flag a version
  deprecated (it still validates and emits) and emit ``platform.event.deprecated``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.access import AccessPrincipal, requires
from aip.platform.context import get_context
from aip.platform.db.session import with_tenant
from aip.platform.events.outbox import Aggregate, emit
from aip.platform.events.registry import (
    PLATFORM_EVENT_DEPRECATED,
    EventSpec,
    registry,
)
from aip.platform.modules.registry import LoadedModule

__all__ = ["create_router"]

_COUNTS_WINDOW = timedelta(hours=24)
# Stable namespace so a deprecation's aggregate id is derived from the event name+version.
_EVENT_NS = UUID("6f1b2d3c-0000-4000-8000-000000000e06")

EVENTS_MANAGE = Depends(requires("platform.events.manage"))
Operator = Annotated[AccessPrincipal, EVENTS_MANAGE]

EventStatus = Literal["active", "deprecated"]


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )


class EventSummary(_Model):
    name: str
    version: int
    module: str
    status: EventStatus
    subscribers: list[str]
    # Explicit aliases: to_camel would render "published24H"/"failed24H".
    published_24h: int = Field(serialization_alias="published24h")
    failed_24h: int = Field(serialization_alias="failed24h")


class EventCatalogue(_Model):
    events: list[EventSummary]


class EventVersionDetail(_Model):
    version: int
    status: EventStatus
    subscribers: list[str]
    # Exposed as the JSON key "schema"; the Python name avoids shadowing BaseModel.schema.
    payload_schema: dict[str, object] = Field(serialization_alias="schema")


class EventDetail(_Model):
    name: str
    versions: list[EventVersionDetail]


class DeprecateResult(_Model):
    name: str
    version: int
    status: EventStatus
    deprecated_at: datetime
    deprecated_by: UUID | None


def _subscribers(modules: Sequence[LoadedModule]) -> dict[tuple[str, int], list[str]]:
    """Map ``(event_name, version)`` to the sorted module ids that subscribe to it (manifests)."""
    subs: dict[tuple[str, int], set[str]] = {}
    for module in modules:
        for ref in module.manifest.subscribes:
            subs.setdefault((ref.name, ref.version), set()).add(module.id)
    return {key: sorted(ids) for key, ids in subs.items()}


async def _counts(conn: AsyncConnection, since: datetime) -> dict[tuple[str, int], tuple[int, int]]:
    """``(name, version) -> (published, failed)`` from the cross-tenant counts function."""
    result = await conn.execute(
        text(
            "SELECT event_name, event_version, published, failed FROM platform_event_counts(:since)"
        ),
        {"since": since},
    )
    return {(r.event_name, r.event_version): (int(r.published), int(r.failed)) for r in result}


async def _statuses(conn: AsyncConnection) -> dict[tuple[str, int], EventStatus]:
    """``(name, version) -> status`` from ``platform_event_status`` (default ``active``)."""
    result = await conn.execute(
        text("SELECT event_name, event_version, status FROM platform_event_status")
    )
    return {(r.event_name, r.event_version): r.status for r in result}


def create_router(modules: Sequence[LoadedModule]) -> APIRouter:
    """Build the event-catalogue router for an app's resolved module list (for subscribers)."""
    subscribers = _subscribers(modules)
    router = APIRouter(prefix="/admin/platform/events", tags=["platform"])

    def _subs(name: str, version: int) -> list[str]:
        return subscribers.get((name, version), [])

    @router.get("", response_model=EventCatalogue, dependencies=[EVENTS_MANAGE])
    async def list_events(  # pyright: ignore[reportUnusedFunction]
        module: Annotated[str | None, Query()] = None,
        status_filter: Annotated[EventStatus | None, Query(alias="status")] = None,
        version: Annotated[int | None, Query(ge=1)] = None,
    ) -> EventCatalogue:
        since = datetime.now(UTC) - _COUNTS_WINDOW
        async with with_tenant(get_context()) as conn:
            counts = await _counts(conn, since)
            statuses = await _statuses(conn)
        rows: list[EventSummary] = []
        for spec in registry.specs():
            status_value = statuses.get((spec.name, spec.version), "active")
            if module is not None and spec.owner != module:
                continue
            if version is not None and spec.version != version:
                continue
            if status_filter is not None and status_value != status_filter:
                continue
            published, failed = counts.get((spec.name, spec.version), (0, 0))
            rows.append(
                EventSummary(
                    name=spec.name,
                    version=spec.version,
                    module=spec.owner,
                    status=status_value,
                    subscribers=_subs(spec.name, spec.version),
                    published_24h=published,
                    failed_24h=failed,
                )
            )
        return EventCatalogue(events=rows)

    @router.get("/{event_name}", response_model=EventDetail, dependencies=[EVENTS_MANAGE])
    async def get_event(  # pyright: ignore[reportUnusedFunction]
        event_name: Annotated[str, Path()],
    ) -> EventDetail:
        specs = registry.versions(event_name)
        if not specs:
            raise HTTPException(status_code=404, detail=f"unknown event {event_name}")
        async with with_tenant(get_context()) as conn:
            statuses = await _statuses(conn)
        return EventDetail(
            name=event_name,
            versions=[
                EventVersionDetail(
                    version=spec.version,
                    status=statuses.get((spec.name, spec.version), "active"),
                    subscribers=_subs(spec.name, spec.version),
                    payload_schema=spec.json_schema(),
                )
                for spec in specs
            ],
        )

    @router.post(
        "/{event_name}/versions/{version}/deprecate",
        response_model=DeprecateResult,
        status_code=status.HTTP_200_OK,
    )
    async def deprecate_event_version(  # pyright: ignore[reportUnusedFunction]
        principal: Operator,
        event_name: Annotated[str, Path()],
        version: Annotated[int, Path(ge=1)],
    ) -> DeprecateResult:
        spec: EventSpec | None = registry.spec(event_name, version)
        if spec is None:
            raise HTTPException(status_code=404, detail=f"unknown event {event_name} v{version}")
        actor = principal.actor_id
        async with with_tenant(get_context()) as conn:
            row = (
                await conn.execute(
                    text("""
                    INSERT INTO platform_event_status
                      (event_name, event_version, status, deprecated_at, deprecated_by)
                    VALUES (:name, :version, 'deprecated', now(), :by)
                    ON CONFLICT (event_name, event_version) DO UPDATE
                      SET status = 'deprecated', deprecated_at = now(),
                          deprecated_by = excluded.deprecated_by, updated_at = now()
                    RETURNING deprecated_at, deprecated_by
                    """),
                    {"name": event_name, "version": version, "by": actor},
                )
            ).one()
            await emit(
                conn,
                PLATFORM_EVENT_DEPRECATED,
                1,
                Aggregate("platform_event", uuid5(_EVENT_NS, f"{event_name}.v{version}")),
                {
                    "event_name": event_name,
                    "event_version": version,
                    "deprecated_by": None if actor is None else str(actor),
                },
            )
        return DeprecateResult(
            name=event_name,
            version=version,
            status="deprecated",
            deprecated_at=row.deprecated_at,
            deprecated_by=row.deprecated_by,
        )

    return router
