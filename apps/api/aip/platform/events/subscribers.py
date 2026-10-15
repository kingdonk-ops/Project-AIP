"""Outbox subscribers: ``@subscriber(event_name, version)`` (ARCH-07, ADR 0003).

A module reacts to another module's events by registering a handler in its own ``events.py``::

    @subscriber("widget.created", 1)
    async def index_widget(conn: AsyncConnection, event: DomainEvent) -> None:
        ...

The dispatcher calls the handler on an ``aip_app`` connection inside ``with_tenant`` for the
event's tenant, so RLS applies as for a request. A handler may run more than once for the same
event (a retry after a later subscriber failed, or a crash before the publish was recorded), so it
must be idempotent on ``event.id``.

The owning module is the package that contains the ``events.py`` (``aip.modules.<id>.events``).
Each subscription must also be listed under ``subscribes`` in that module's manifest;
:func:`verify_manifest_subscribers` fails boot otherwise, and :meth:`SubscriberRegistry.for_modules`
returns only the subscribers of modules that are actually loaded, so a disabled module's handlers
never run.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "DomainEvent",
    "Handler",
    "ManifestSubscriberMismatchError",
    "Subscriber",
    "SubscriberRegistry",
    "owner_of",
    "subscriber",
    "subscribers",
    "verify_manifest_subscribers",
]


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """One outbox row as a subscriber sees it (payload already validated by ``emit``)."""

    id: UUID
    tenant_id: UUID
    project_id: UUID | None
    asset_id: UUID | None
    event_name: str
    event_version: int
    aggregate_type: str
    aggregate_id: UUID
    payload: Mapping[str, Any]
    actor_id: UUID | None
    occurred_at: datetime
    attempts: int


Handler = Callable[[AsyncConnection, DomainEvent], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Subscriber:
    event_name: str
    version: int
    owner: str
    handler: Handler

    @property
    def name(self) -> str:
        """``<owner>.<handler>``, as logged and stored in ``last_error``."""
        return f"{self.owner}.{getattr(self.handler, '__name__', 'handler')}"


class ManifestSubscriberMismatchError(Exception):
    """A module registers a subscriber its manifest does not list under ``subscribes``."""


def owner_of(handler: Callable[..., Any]) -> str:
    """The module id that owns ``handler``: the package segment before ``.events``."""
    parts = handler.__module__.split(".")
    if len(parts) < 2 or parts[-1] != "events":
        raise ValueError(
            f"subscriber {handler.__module__}.{handler.__name__} must live in a module's events.py"
        )
    return parts[-2]


class SubscriberRegistry:
    """Every registered subscriber, by ``(event_name, version)``."""

    __slots__ = ("_subs",)

    def __init__(self) -> None:
        self._subs: list[Subscriber] = []

    def register(self, event_name: str, version: int, handler: Handler, owner: str) -> None:
        if not event_name or version < 1 or not owner:
            raise ValueError(f"invalid subscription {event_name!r} v{version} owner {owner!r}")
        if any(
            s.handler is handler and s.event_name == event_name and s.version == version
            for s in self._subs
        ):
            return  # the same events.py imported twice
        self._subs.append(Subscriber(event_name, version, owner, handler))

    def subscriber(
        self, event_name: str, version: int, *, owner: str | None = None
    ) -> Callable[[Handler], Handler]:
        """Decorator form of :meth:`register`; ``owner`` defaults to :func:`owner_of`."""

        def decorate(handler: Handler) -> Handler:
            self.register(event_name, version, handler, owner or owner_of(handler))
            return handler

        return decorate

    def all(self) -> list[Subscriber]:
        return list(self._subs)

    def for_event(self, event_name: str, version: int) -> list[Subscriber]:
        return [s for s in self._subs if s.event_name == event_name and s.version == version]

    def for_modules(self, module_ids: Iterable[str]) -> SubscriberRegistry:
        """A registry holding only the subscribers owned by ``module_ids`` (the loaded modules)."""
        ids = set(module_ids)
        selected = SubscriberRegistry()
        selected._subs = [s for s in self._subs if s.owner in ids]
        return selected


subscribers = SubscriberRegistry()
"""The process-wide registry; ``@subscriber`` registers here at import of a module's events.py."""


def subscriber(event_name: str, version: int) -> Callable[[Handler], Handler]:
    """Register the decorated handler for ``event_name`` v``version`` (see module docstring)."""
    return subscribers.subscriber(event_name, version)


def verify_manifest_subscribers(
    modules: Iterable[Any], reg: SubscriberRegistry = subscribers
) -> None:
    """Fail boot if a loaded module subscribes to an event its manifest does not list.

    Only subscribers owned by a module in ``modules`` are checked (as for events, the process-wide
    registry may hold subscribers of modules this process does not load).
    """
    by_id = {module.id: module for module in modules}
    for sub in reg.all():
        module = by_id.get(sub.owner)
        if module is None:
            continue
        declared = {(ref.name, ref.version) for ref in module.manifest.subscribes}
        if (sub.event_name, sub.version) not in declared:
            raise ManifestSubscriberMismatchError(
                f"module {sub.owner}: {sub.name} subscribes to {sub.event_name} v{sub.version} "
                "but its manifest does not list it under subscribes"
            )
