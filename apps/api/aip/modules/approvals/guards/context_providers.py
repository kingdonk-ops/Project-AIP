"""Read-only guard facts from host modules (APPROVALS-02 Part B).

A host module registers one provider per record type at import time::

    from aip.modules.approvals.api import register_guard_context_provider

    async def inspection_facts(conn: AsyncConnection, record_id: UUID) -> dict[str, object]:
        return {"allPhotosClean": await photos_clean(conn, record_id)}

    register_guard_context_provider("inspection", inspection_facts)

The provider gets the transition's ``with_tenant`` connection (RLS applies) and reads only its own
module's tables; approvals never reads another module's tables. Its result becomes the guard's
``record``. A record type with no provider gets ``{}``.

The same host module registers a ``RecordResolver`` for its record type: given a record id it
returns the record's ``RecordRef`` (its real project) or ``None`` when no such record is visible.
``POST /approvals/instances`` starts a workflow only for a record type with a resolver, and always
on the resolved project, never on one the client names (ADR 0035).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "GuardContextProvider",
    "RecordRef",
    "RecordResolver",
    "provider_for",
    "register_guard_context_provider",
    "register_record_resolver",
    "resolver_for",
    "unregister_guard_context_provider",
    "unregister_record_resolver",
]

GuardContextProvider = Callable[[AsyncConnection, UUID], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class RecordRef:
    """What approvals may know about a host record: the project it belongs to."""

    project_id: UUID | None


RecordResolver = Callable[[AsyncConnection, UUID], Awaitable[RecordRef | None]]

_providers: dict[str, GuardContextProvider] = {}
_resolvers: dict[str, RecordResolver] = {}


def register_guard_context_provider(record_type: str, provider: GuardContextProvider) -> None:
    """Register the facts provider for ``record_type``; a second one for the same type fails."""
    if record_type in _providers:
        raise ValueError(f"a guard context provider for {record_type} is already registered")
    _providers[record_type] = provider


def unregister_guard_context_provider(record_type: str) -> None:
    """Remove the provider for ``record_type`` (tests, and a module being disabled)."""
    _providers.pop(record_type, None)


def provider_for(record_type: str) -> GuardContextProvider | None:
    return _providers.get(record_type)


def register_record_resolver(record_type: str, resolver: RecordResolver) -> None:
    """Register how to find a ``record_type`` record's project; a second one fails."""
    if record_type in _resolvers:
        raise ValueError(f"a record resolver for {record_type} is already registered")
    _resolvers[record_type] = resolver


def unregister_record_resolver(record_type: str) -> None:
    _resolvers.pop(record_type, None)


def resolver_for(record_type: str) -> RecordResolver | None:
    return _resolvers.get(record_type)
