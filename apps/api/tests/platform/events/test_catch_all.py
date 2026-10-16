"""AUDIT-02: catch-all outbox subscriptions (``"*"``) in the ARCH-07 subscriber registry."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from aip.platform.events.subscribers import (
    ANY_EVENT,
    DomainEvent,
    ManifestSubscriberMismatchError,
    SubscriberRegistry,
    verify_manifest_subscribers,
)
from aip.platform.modules.manifest import EventRef


async def _first(conn: Any, event: DomainEvent) -> None: ...


async def _catch_all(conn: Any, event: DomainEvent) -> None: ...


def _module(module_id: str, *subscribes: tuple[str, int]) -> Any:
    refs = [EventRef(name=name, version=version) for name, version in subscribes]
    return SimpleNamespace(id=module_id, manifest=SimpleNamespace(subscribes=refs))


def test_a_catch_all_subscriber_runs_for_every_event_after_the_events_own() -> None:
    reg = SubscriberRegistry()
    reg.register(ANY_EVENT, 1, _catch_all, "audit")
    reg.register("widget.created", 1, _first, "widgets")
    assert [s.handler for s in reg.for_event("widget.created", 1)] == [_first, _catch_all]
    assert [s.handler for s in reg.for_event("anything.else", 7)] == [_catch_all]


def test_a_catch_all_subscriber_needs_its_manifest_entry() -> None:
    reg = SubscriberRegistry()
    reg.register(ANY_EVENT, 1, _catch_all, "audit")
    verify_manifest_subscribers([_module("audit", (ANY_EVENT, 1))], reg)
    with pytest.raises(ManifestSubscriberMismatchError):
        verify_manifest_subscribers([_module("audit")], reg)


def test_a_disabled_module_s_catch_all_never_runs() -> None:
    reg = SubscriberRegistry()
    reg.register(ANY_EVENT, 1, _catch_all, "audit")
    assert reg.for_modules(["projects"]).for_event("project.created", 1) == []
