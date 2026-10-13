"""``emit``: write a domain event in the caller's transaction (ARCH-05, ADR 0003).

::

    async with with_tenant(get_context()) as conn:
        await conn.execute(insert(widgets).values(...))
        await emit(conn, "widget.created", 1, Aggregate("widget", widget_id), {...})

The event commits or rolls back with the state change, because ``emit`` only ever uses the
connection it is given. The payload is validated against the registered model before any SQL
runs, and tenant, project and actor come from the request context, never from the caller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.context import get_context, new_request_id
from aip.platform.events.lookup import DictEventSchemaLookup, EventSchemaLookup
from aip.platform.events.tables import domain_events

__all__ = ["Aggregate", "EventValidationError", "emit", "event_schemas"]

# The process-wide payload models; modules register theirs at import time (ARCH-06 replaces it).
event_schemas = DictEventSchemaLookup()


@dataclass(frozen=True, slots=True)
class Aggregate:
    """The record an event is about, e.g. ``Aggregate("project", project_id)``."""

    type: str
    id: UUID


class EventValidationError(ValueError):
    """The event is unknown, or its payload does not match the registered model."""

    def __init__(self, event_name: str, version: int, fields: tuple[str, ...], detail: str) -> None:
        self.event_name = event_name
        self.version = version
        self.fields = fields
        super().__init__(f"{event_name} v{version}: {detail}")


def _validate(
    schemas: EventSchemaLookup, event_name: str, version: int, payload: Mapping[str, Any]
) -> dict[str, Any]:
    model = schemas.schema_for(event_name, version)
    if model is None:
        raise EventValidationError(event_name, version, (), "no payload model is registered")
    try:
        return model.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        fields = tuple(dict.fromkeys(".".join(str(p) for p in e["loc"]) for e in exc.errors()))
        raise EventValidationError(
            event_name, version, fields, f"invalid payload fields: {', '.join(fields)}"
        ) from None


async def emit(
    conn: AsyncConnection,
    event_name: str,
    version: int,
    aggregate: Aggregate,
    payload: Mapping[str, Any],
    *,
    asset_id: UUID | None = None,
    schemas: EventSchemaLookup | None = None,
) -> UUID:
    """Insert one event on ``conn`` (the caller's ``with_tenant`` connection); return its id.

    Raises ``EventValidationError`` before touching the database if the event is unknown or the
    payload is invalid, and ``ContextMissingError`` outside a request context.
    """
    body = _validate(event_schemas if schemas is None else schemas, event_name, version, payload)
    ctx = get_context()
    event_id = UUID(new_request_id())  # the platform's UUIDv7 generator
    await conn.execute(
        insert(domain_events).values(
            id=event_id,
            tenant_id=ctx.tenant_id,
            project_id=ctx.project_id,
            asset_id=asset_id,
            event_name=event_name,
            event_version=version,
            aggregate_type=aggregate.type,
            aggregate_id=aggregate.id,
            payload=body,
            actor_id=ctx.actor_id,
            occurred_at=datetime.now(UTC),
        )
    )
    return event_id
