"""Domain events terms publishes and subscribes to (via the outbox, ADR 0003).

``terms.pack.activated`` v1 (``{packId, versionId, version, code}``) is emitted when a tenant's
pack version becomes active. Terms subscribes to it itself: the handler bumps the tenant's
terminology cache version, so the next resolve reads the new text. Bumping twice is harmless, so
the handler is idempotent on ``event.id``; a Redis error fails the delivery and the dispatcher
retries it.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.events import register_event
from aip.platform.events.subscribers import DomainEvent, subscriber

from .cache import get_cache

__all__ = ["TERMS_PACK_ACTIVATED", "PackActivated", "invalidate_on_pack_activated"]

TERMS_PACK_ACTIVATED = "terms.pack.activated"


class PackActivated(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    pack_id: UUID
    version_id: UUID
    version: int
    code: str


register_event(TERMS_PACK_ACTIVATED, 1, PackActivated, "terms")


@subscriber(TERMS_PACK_ACTIVATED, 1)
async def invalidate_on_pack_activated(conn: AsyncConnection, event: DomainEvent) -> None:
    await get_cache().bump(event.tenant_id)
