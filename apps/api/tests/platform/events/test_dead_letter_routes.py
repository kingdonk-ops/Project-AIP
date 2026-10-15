"""ARCH-07: the dead-letter API (integration + e2e journey, real Postgres).

The app, users and the ``platform.events.manage`` grant are the ARCH-06 catalogue fixtures:
``alice`` (kaefer-demo) is the operator, ``carol`` (same tenant, no grant) and ``bob`` (tenant B)
are not. Events go through the real dispatcher, claiming as ``aip_jobs`` and running the fixture
subscriber as ``aip_app``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aip.platform.db.engine import EngineSettings, create_app_engine
from aip.platform.db.templates import render_template
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.registry import PLATFORM_OUTBOX_DISCARDED, PLATFORM_OUTBOX_RETRIED
from aip.platform.events.subscribers import DomainEvent, SubscriberRegistry
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    APP,
    JOBS,
    TenantDb,
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

from .test_catalogue_routes import (  # noqa: F401 - pytest fixtures and helpers
    BOB,
    CAROL,
    OPERATOR,
    app,
    client,
    db,
    su_execute,
    su_fetch,
)

URL = "/api/v1/admin/platform/events/dead-letter"
FAIL_FLAG = "FIXTURE_SUBSCRIBER_FAIL"
DEAD_ONCE = DispatchSettings(max_attempts=1)


@pytest.fixture
async def engines(db: TenantDb) -> AsyncIterator[tuple[AsyncEngine, AsyncEngine]]:  # noqa: F811
    jobs = create_app_engine(EngineSettings(url=db.db.role_url(JOBS)))
    app_engine = create_app_engine(EngineSettings(url=db.db.role_url(APP)))
    try:
        yield jobs, app_engine
    finally:
        await jobs.dispose()
        await app_engine.dispose()


def widget_feed_subscriber() -> SubscriberRegistry:
    """The fixture ``widgets`` subscriber: records each widget, or fails while the flag is on."""
    reg = SubscriberRegistry()

    async def feed_widget(conn: AsyncConnection, event: DomainEvent) -> None:
        if os.environ.get(FAIL_FLAG) == "1":
            raise RuntimeError("fixture subscriber is set to fail")
        await conn.execute(
            text(
                "INSERT INTO widget_feed (id, tenant_id, name) VALUES (:id, :t, :name)"
                " ON CONFLICT (id) DO NOTHING"  # idempotent on the event id
            ),
            {"id": event.id, "t": event.tenant_id, "name": event.payload["name"]},
        )

    reg.register("widget.created", 1, feed_widget, "widgets")
    return reg


async def insert_widget_event(db: TenantDb, tenant: UUID) -> UUID:  # noqa: F811
    event_id = uuid4()
    await su_execute(
        db,
        "INSERT INTO domain_events (id, tenant_id, event_name, event_version, aggregate_type,"
        f" aggregate_id, payload) VALUES ('{event_id}', '{tenant}', 'widget.created', 1, 'widget',"
        f' \'{uuid4()}\', \'{{"widget_id": "{uuid4()}", "name": "w1"}}\'::jsonb);',
    )
    return event_id


async def dead_letter(db: TenantDb, tenant: UUID = TENANT_A_ID) -> UUID:  # noqa: F811
    """Insert one event and dead-letter it by failing its only delivery."""
    event_id = await insert_widget_event(db, tenant)
    await su_execute(
        db,
        f"UPDATE domain_events SET attempts = 1, last_error = 'boom', dead_lettered_at = now()"
        f" WHERE id = '{event_id}'",
    )
    return event_id


async def test_operator_sees_the_journey_from_failure_to_retry(
    app: FastAPI,  # noqa: F811
    client: httpx.AsyncClient,  # noqa: F811
    db: TenantDb,  # noqa: F811
    engines: tuple[AsyncEngine, AsyncEngine],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs, app_engine = engines
    await su_execute(db, render_template("tenant_table", table="widget_feed", columns="name text"))
    reg = widget_feed_subscriber()
    event_id = await insert_widget_event(db, TENANT_A_ID)

    monkeypatch.setenv(FAIL_FLAG, "1")
    result = await dispatch_batch(jobs, app_engine, reg, DEAD_ONCE)
    assert result.dead_lettered == 1

    listed = await client.get(URL, headers=OPERATOR)
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    assert item["id"] == str(event_id) and item["tenantId"] == str(TENANT_A_ID)
    assert item["eventName"] == "widget.created" and item["attempts"] == 1
    assert "fixture subscriber is set to fail" in item["lastError"]
    assert "payload" not in item

    monkeypatch.setenv(FAIL_FLAG, "0")
    retried = await client.post(f"{URL}/{event_id}/retry", headers=OPERATOR)
    assert retried.status_code == 200, retried.text
    assert retried.json()["action"] == "retried"
    assert (await client.get(URL, headers=OPERATOR)).json()["items"] == []

    result = await dispatch_batch(jobs, app_engine, reg, DEAD_ONCE)
    assert result.published >= 1
    assert await su_fetch(db, "SELECT name FROM widget_feed") == [("w1",)]
    audit = await su_fetch(
        db,
        "SELECT tenant_id, payload->>'eventId' FROM domain_events WHERE event_name = $1",
        PLATFORM_OUTBOX_RETRIED,
    )
    assert audit == [(TENANT_A_ID, str(event_id))]
    # A second retry finds nothing in the queue.
    assert (await client.post(f"{URL}/{event_id}/retry", headers=OPERATOR)).status_code == 404


async def test_discard_requires_a_reason(
    client: httpx.AsyncClient,  # noqa: F811
    db: TenantDb,  # noqa: F811
) -> None:
    event_id = await dead_letter(db)
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        response = await client.post(f"{URL}/{event_id}/discard", headers=OPERATOR, json=body)
        assert response.status_code == 422, body

    response = await client.post(
        f"{URL}/{event_id}/discard", headers=OPERATOR, json={"reason": " duplicate import "}
    )
    assert response.status_code == 200, response.text
    assert response.json()["action"] == "discarded"
    (row,) = await su_fetch(
        db,
        "SELECT discard_reason, discarded_by IS NOT NULL FROM domain_events WHERE id = $1",
        event_id,
    )
    assert row == ("duplicate import", True)
    assert (await client.get(URL, headers=OPERATOR)).json()["items"] == []
    assert (await client.post(f"{URL}/{event_id}/retry", headers=OPERATOR)).status_code == 404
    audit = await su_fetch(
        db,
        "SELECT payload->>'reason' FROM domain_events WHERE event_name = $1",
        PLATFORM_OUTBOX_DISCARDED,
    )
    assert audit == [("duplicate import",)]


async def test_the_list_spans_tenants_and_pages(
    client: httpx.AsyncClient,  # noqa: F811
    db: TenantDb,  # noqa: F811
) -> None:
    ids = {await dead_letter(db, TENANT_A_ID), await dead_letter(db, TENANT_B_ID)}
    ids.add(await dead_letter(db, TENANT_B_ID))
    first = (await client.get(URL, headers=OPERATOR, params={"limit": 2})).json()
    assert len(first["items"]) == 2 and first["nextAfter"] == first["items"][-1]["id"]
    rest = (
        await client.get(URL, headers=OPERATOR, params={"limit": 2, "after": first["nextAfter"]})
    ).json()
    assert rest["nextAfter"] is None
    assert {item["id"] for item in first["items"] + rest["items"]} == {str(i) for i in ids}


async def test_an_unknown_event_is_404(client: httpx.AsyncClient) -> None:  # noqa: F811
    missing = uuid4()
    assert (await client.post(f"{URL}/{missing}/retry", headers=OPERATOR)).status_code == 404
    response = await client.post(f"{URL}/{missing}/discard", headers=OPERATOR, json={"reason": "x"})
    assert response.status_code == 404


@pytest.mark.parametrize("who", [CAROL, BOB], ids=["same-tenant-no-grant", "other-tenant"])
async def test_without_the_permission_every_endpoint_is_403(
    client: httpx.AsyncClient,  # noqa: F811
    db: TenantDb,  # noqa: F811
    who: dict[str, str],
) -> None:
    event_id = await dead_letter(db)
    assert (await client.get(URL, headers=who)).status_code == 403
    assert (await client.post(f"{URL}/{event_id}/retry", headers=who)).status_code == 403
    response = await client.post(f"{URL}/{event_id}/discard", headers=who, json={"reason": "x"})
    assert response.status_code == 403
    rows = await su_fetch(
        db,
        "SELECT dead_lettered_at IS NOT NULL, discarded_at FROM domain_events WHERE id = $1",
        event_id,
    )
    assert rows == [(True, None)]
