"""Report data providers (REPORTS-02), internal to report_engine.

A provider turns one record into the data a report template renders. It is registered per record
type with the permission a user needs to see that record::

    register_provider("project", project_source, view_permission="project.view")

A provider is ``async (conn, record_id, *, context) -> ReportSource``. It runs on the caller's
``with_tenant`` connection (so RLS decides what it sees), reads the record through its owning
module's published interface, and raises ``RecordNotFound`` for a missing record or another
tenant's id. ``context`` is the trigger data (``{}`` for a manual render). ``data`` must be plain
JSON (strings, numbers, booleans, lists, dicts) and hold no clock value: the snapshot hash is taken
over it, so unchanged data gives the same hash. ``files`` lists ``{fileId, role}`` stored files the
template may show; ``time_zone_hint`` is the record's IANA zone (``None`` falls back to UTC).

``providers/project.py`` registers ``project``; REPORTS-03 adds ``inspection``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "Provider",
    "ProviderEntry",
    "RecordNotFound",
    "ReportSource",
    "SourceFile",
    "get_provider",
    "register_provider",
    "registered_record_types",
    "unregister_provider",
]


class RecordNotFound(LookupError):  # noqa: N818 - name fixed by the REPORTS-02 spec
    """The record does not exist, or the caller's tenant (RLS) cannot see it."""


@dataclass(frozen=True, slots=True)
class SourceFile:
    """A stored file the template may show, and the role it plays (``photo``, ``signature``...)."""

    file_id: UUID
    role: str


@dataclass(frozen=True, slots=True)
class ReportSource:
    """What a provider returns for one record."""

    project_id: UUID | None
    record_version: int | None
    data: Mapping[str, Any]
    files: tuple[SourceFile, ...] = field(default_factory=tuple[SourceFile, ...])
    time_zone_hint: str | None = None


Provider = Callable[..., Awaitable[ReportSource]]


@dataclass(frozen=True, slots=True)
class ProviderEntry:
    provider: Provider
    view_permission: str


_providers: dict[str, ProviderEntry] = {}


def register_provider(record_type: str, provider: Provider, *, view_permission: str) -> None:
    """Register ``provider`` for ``record_type``. The same registration twice is a no-op; a
    different provider for a known type raises ``ValueError``."""
    entry = ProviderEntry(provider=provider, view_permission=view_permission)
    existing = _providers.get(record_type)
    if existing is not None and existing != entry:
        raise ValueError(f"a report data provider is already registered for {record_type!r}")
    _providers[record_type] = entry


def unregister_provider(record_type: str) -> None:
    """Forget ``record_type`` (tests only). Unknown types are ignored."""
    _providers.pop(record_type, None)


def get_provider(record_type: str) -> ProviderEntry | None:
    return _providers.get(record_type)


def registered_record_types() -> frozenset[str]:
    return frozenset(_providers)


async def call_provider(
    entry: ProviderEntry,
    conn: AsyncConnection,
    record_id: UUID,
    *,
    context: Mapping[str, Any] | None = None,
) -> ReportSource:
    """Run ``entry``'s provider for ``record_id`` (``context`` defaults to ``{}``)."""
    return await entry.provider(conn, record_id, context=dict(context or {}))
