"""REPORTS-03 unit tests: the auto-render subscriber with a fake render service (no database)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.report_engine import events as report_events
from aip.modules.report_engine.auto_render import AutoRender
from aip.platform.events.subscribers import DomainEvent, subscribers
from aip.platform.http import DomainError

INSPECTION = UUID("0192f0a1-0000-7000-8000-00000000a001")
SUPERVISOR = UUID("00000000-0000-4000-8000-0000000005e1")
BOTH = [{"key": "inspection", "variant": "internal"}, {"key": "inspection", "variant": "client"}]


class FakeConn:
    """Counts savepoints and whether each one was rolled back."""

    def __init__(self) -> None:
        self.savepoints: list[str] = []

    @asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[None]:
        try:
            yield
        except BaseException:
            self.savepoints.append("rolled back")
            raise
        self.savepoints.append("released")


class FakeRenderer:
    def __init__(self, fail_first: DomainError | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_first = fail_first

    async def request_render(self, conn: AsyncConnection, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.fail_first is not None and len(self.calls) == 1:
            raise self.fail_first


def _event(to: str) -> DomainEvent:
    return DomainEvent(
        id=uuid4(),
        tenant_id=uuid4(),
        project_id=None,
        asset_id=None,
        event_name="inspection.state_changed",
        event_version=1,
        aggregate_type="inspection",
        aggregate_id=INSPECTION,
        payload={
            "inspectionId": str(INSPECTION),
            "from": "supervisor_review",
            "to": to,
            "action": "mark_performed",
        },
        actor_id=SUPERVISOR,
        occurred_at=datetime(2026, 10, 30, 3, 0, tzinfo=UTC),
        attempts=1,
    )


def _auto(renderer: FakeRenderer, asked: list[str] | None = None) -> AutoRender:
    async def list_templates(
        conn: AsyncConnection, *, record_type: str, state: str
    ) -> list[dict[str, Any]]:
        assert record_type == "inspection"
        if asked is not None:
            asked.append(state)
        return BOTH if state == "performed" else []

    return AutoRender(renderer, list_templates)


async def test_another_state_renders_nothing() -> None:
    renderer, asked = FakeRenderer(), []
    await _auto(renderer, asked).on_inspection_state_changed(
        cast(AsyncConnection, FakeConn()), _event("in_progress")
    )
    assert renderer.calls == [] and asked == ["in_progress"]


async def test_the_approved_state_queues_both_variants_with_event_keys() -> None:
    renderer, conn = FakeRenderer(), FakeConn()
    event = _event("performed")
    await _auto(renderer).on_inspection_state_changed(cast(AsyncConnection, conn), event)
    assert [c["idempotency_key"] for c in renderer.calls] == [
        f"auto:{event.id}:inspection:internal",
        f"auto:{event.id}:inspection:client",
    ]
    first = renderer.calls[0]
    assert first["record_type"] == "inspection" and first["record_id"] == INSPECTION
    assert first["requested_by"] == SUPERVISOR and first["trigger_event_id"] == event.id
    assert first["context"] == {"approvedAt": event.occurred_at, "approvedBy": SUPERVISOR}
    assert conn.savepoints == ["released", "released"]


async def test_a_report_error_rolls_back_its_savepoint_and_the_next_still_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    renderer = FakeRenderer(fail_first=DomainError(404, "RECORD_NOT_FOUND"))
    conn, event = FakeConn(), _event("performed")
    with caplog.at_level(logging.WARNING, logger="aip.modules.report_engine.auto_render"):
        await _auto(renderer).on_inspection_state_changed(cast(AsyncConnection, conn), event)
    assert len(renderer.calls) == 2
    assert conn.savepoints == ["rolled back", "released"]
    (record,) = [r for r in caplog.records if "auto-render" in r.getMessage()]
    message = record.getMessage()
    assert str(event.id) in message and "RECORD_NOT_FOUND" in message
    assert "inspection/internal" in message


async def test_any_other_error_is_raised_for_a_retry() -> None:
    class Broken(FakeRenderer):
        async def request_render(self, conn: AsyncConnection, **kwargs: Any) -> None:
            raise RuntimeError("database went away")

    with pytest.raises(RuntimeError):
        await _auto(Broken()).on_inspection_state_changed(
            cast(AsyncConnection, FakeConn()), _event("performed")
        )


def test_the_subscriber_is_registered_for_report_engine() -> None:
    found = subscribers.for_modules(["report_engine"]).for_event("inspection.state_changed", 1)
    assert [s.handler for s in found] == [report_events.render_on_inspection_state_changed]
