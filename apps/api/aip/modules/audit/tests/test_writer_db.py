"""AUDIT-02 integration tests: the outbox audit writer on real Postgres with the real dispatcher.

Events are emitted as ``aip_app`` inside ``with_tenant``, the dispatcher claims as ``aip_jobs`` and
the audit subscriber appends as ``aip_audit_writer``, exactly as in the worker. Event payloads are
validated against permissive test schemas, so any event name can be emitted. Rows that must be
seen across tenants are read as the test superuser.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.audit import expect_audited
from tests.fixtures.postgres import Outbox, _fetch  # pyright: ignore[reportPrivateUsage]

from aip.modules.audit import events as audit_events  # registers the catch-all subscriber
from aip.modules.audit import writer as writer_module
from aip.modules.audit.api import AuditApi, SecurityEventInput
from aip.modules.audit.chain_hash import GENESIS_PREV_HASH, compute_hash
from aip.modules.audit.security_chain import security_chain_entry
from aip.platform.context import RequestContext, use_context
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, DictEventSchemaLookup, emit
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.subscribers import DomainEvent, subscribers

from .test_repository_db import _assert_valid_chain  # pyright: ignore[reportPrivateUsage]


class Free(BaseModel):
    model_config = ConfigDict(extra="allow")


NAMES = ["project.updated", "auth.login.succeeded", "user.deactivated", "widget.created"]
SCHEMAS = DictEventSchemaLookup({(name, 1): Free for name in NAMES})
AUDIT_ONLY = subscribers.for_modules(["audit"])
assert audit_events.write_audit_entries in [s.handler for s in AUDIT_ONLY.all()]


async def emit_events(
    outbox: Outbox,
    name: str,
    payloads: list[dict[str, Any]],
    *,
    tenant: UUID = TENANT_A_ID,
    actor: UUID = ALICE_ID,
    aggregate: Aggregate | None = None,
) -> list[UUID]:
    ctx = RequestContext(tenant_id=tenant, request_id=f"test-{uuid4().hex}", actor_id=actor)
    ids: list[UUID] = []
    async with use_context(ctx), with_tenant(ctx, engine=outbox.app) as conn:
        for payload in payloads:
            agg = aggregate or Aggregate("project", uuid4())
            ids.append(await emit(conn, name, 1, agg, payload, schemas=SCHEMAS))
    return ids


async def dispatch_all(outbox: Outbox) -> None:
    settings = DispatchSettings(batch_size=100)
    while (await dispatch_batch(outbox.jobs, outbox.app, AUDIT_ONLY, settings)).claimed:
        pass


async def su(outbox: Outbox, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(outbox.db.superuser_url, sql, *args)


async def audit_rows(outbox: Outbox, tenant: UUID = TENANT_A_ID) -> list[dict[str, Any]]:
    rows = await su(
        outbox,
        "SELECT row_to_json(a)::text FROM audit_log a WHERE tenant_id = $1 ORDER BY seq",
        tenant,
    )
    return [_restore(json.loads(r[0])) for r in rows]


async def security_rows(outbox: Outbox, tenant: UUID = TENANT_A_ID) -> list[dict[str, Any]]:
    rows = await su(
        outbox,
        "SELECT row_to_json(s)::text FROM security_audit_events s"
        " WHERE tenant_id = $1 ORDER BY seq",
        tenant,
    )
    return [_restore(json.loads(r[0])) for r in rows]


def _restore(row: dict[str, Any]) -> dict[str, Any]:
    """``row_to_json`` gives text for uuids, timestamps and bytea; turn them back."""
    from datetime import datetime

    for key in (
        "id",
        "tenant_id",
        "actor_id",
        "on_behalf_of_id",
        "record_id",
        "project_id",
        "asset_id",
        "source_event_id",
        "supersedes_id",
    ):
        if row.get(key):
            row[key] = UUID(row[key])
    for key in ("prev_hash", "hash"):
        row[key] = bytes.fromhex(row[key].removeprefix("\\x"))
    row["occurred_at"] = datetime.fromisoformat(row["occurred_at"])
    if "flags" in row and row["flags"] is None:
        row["flags"] = []
    return row


def assert_valid_security_chain(rows: list[dict[str, Any]]) -> None:
    prev = GENESIS_PREV_HASH
    for row in rows:
        assert row["prev_hash"] == prev, f"seq {row['seq']} prev_hash broken"
        assert row["hash"] == compute_hash(prev, security_chain_entry(row)), f"seq {row['seq']}"
        prev = row["hash"]


async def test_fifty_events_give_seq_one_to_fifty_with_a_valid_chain(outbox: Outbox) -> None:
    await emit_events(outbox, "project.updated", [{"after": {"n": n}} for n in range(50)])
    await dispatch_all(outbox)
    rows = await audit_rows(outbox)
    assert [r["seq"] for r in rows] == list(range(1, 51))
    assert {r["stream"] for r in rows} == {"audit"}
    _assert_valid_chain(rows)
    published = await su(
        outbox, "SELECT count(*) FROM domain_events WHERE published_at IS NOT NULL"
    )
    assert published == [(50,)]


async def test_redelivery_adds_nothing(outbox: Outbox) -> None:
    await emit_events(outbox, "project.updated", [{"after": {"n": n}} for n in range(5)])
    await dispatch_all(outbox)
    # Deliver every event again, as a crash between delivery and publish would.
    raw = await su(
        outbox,
        "SELECT id, tenant_id, project_id, asset_id, event_name, event_version, aggregate_type,"
        " aggregate_id, payload::text, actor_id, occurred_at, attempts FROM domain_events",
    )
    for row in raw:
        values = list(row)
        values[8] = json.loads(values[8])
        await writer_module.write_event(DomainEvent(*values))
    rows = await audit_rows(outbox)
    assert [r["seq"] for r in rows] == [1, 2, 3, 4, 5]
    _assert_valid_chain(rows)


async def test_a_failed_write_leaves_the_event_unpublished_and_the_retry_writes_it_once(
    outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = writer_module.append_audit_entries
    calls = {"n": 0}

    async def fail_once(*args: Any, **kwargs: Any) -> list[int]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("audit writer pool unavailable")
        return await real(*args, **kwargs)

    monkeypatch.setattr(writer_module, "append_audit_entries", fail_once)
    [event_id] = await emit_events(outbox, "project.updated", [{"after": {"n": 1}}])
    await dispatch_all(outbox)
    state = await su(
        outbox,
        "SELECT attempts, published_at, last_error FROM domain_events WHERE id = $1",
        event_id,
    )
    assert state[0][0] == 1 and state[0][1] is None and state[0][2].startswith("audit.")
    assert await audit_rows(outbox) == []

    await su(outbox, "UPDATE domain_events SET next_attempt_at = now() WHERE id = $1", event_id)
    await dispatch_all(outbox)
    assert [r["seq"] for r in await audit_rows(outbox)] == [1]
    published = await su(outbox, "SELECT published_at FROM domain_events WHERE id = $1", event_id)
    assert published[0][0] is not None


async def test_an_auth_event_goes_only_to_the_security_stream(outbox: Outbox) -> None:
    await emit_events(
        outbox,
        "auth.login.succeeded",
        [{"sourceIp": "203.0.113.7", "device": "Firefox", "authStrength": "mfa"}],
        aggregate=Aggregate("user", ALICE_ID),
    )
    await dispatch_all(outbox)
    assert await audit_rows(outbox) == []
    rows = await security_rows(outbox)
    assert [(r["seq"], r["event_type"], r["source_ip"], r["auth_strength"]) for r in rows] == [
        (1, "auth.login.succeeded", "203.0.113.7", "mfa")
    ]
    assert rows[0]["actor_id"] == ALICE_ID and rows[0]["target_ref"] == f"user:{ALICE_ID}"
    assert_valid_security_chain(rows)


async def test_user_deactivated_is_written_to_both_streams(outbox: Outbox) -> None:
    await emit_events(
        outbox, "user.deactivated", [{"userId": str(BOB_ID)}], aggregate=Aggregate("user", BOB_ID)
    )
    await dispatch_all(outbox)
    assert [r["event_type"] for r in await audit_rows(outbox)] == ["user.deactivated"]
    assert [r["event_type"] for r in await security_rows(outbox)] == ["user.deactivated"]


async def test_secrets_never_reach_either_table(outbox: Outbox) -> None:
    await emit_events(outbox, "project.updated", [{"before": {}, "after": {"password": "hunter2"}}])
    await emit_events(outbox, "auth.login.succeeded", [{"detail": {"otp": "hunter2"}}])
    await dispatch_all(outbox)
    [row] = await audit_rows(outbox)
    assert row["payload"] == {"before": {}, "after": {"password": "[redacted]"}}
    for table in ("audit_log", "security_audit_events"):
        hits = await su(
            outbox,
            f"SELECT count(*) FROM {table} WHERE row_to_json({table})::text LIKE '%hunter2%'",
        )
        assert hits == [(0,)], table


async def test_two_tenants_in_one_batch_get_independent_chains(outbox: Outbox) -> None:
    await emit_events(outbox, "project.updated", [{"after": {"n": 1}}, {"after": {"n": 2}}])
    await emit_events(
        outbox, "project.updated", [{"after": {"n": 3}}], tenant=TENANT_B_ID, actor=BOB_ID
    )
    await dispatch_all(outbox)
    a, b = await audit_rows(outbox, TENANT_A_ID), await audit_rows(outbox, TENANT_B_ID)
    assert ([r["seq"] for r in a], [r["seq"] for r in b]) == ([1, 2], [1])
    _assert_valid_chain(a)
    _assert_valid_chain(b)


async def test_a_recorded_security_event_goes_through_the_outbox(outbox: Outbox) -> None:
    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id=f"test-{uuid4().hex}", actor_id=ALICE_ID)
    async with use_context(ctx), with_tenant(ctx, engine=outbox.app) as conn:
        await AuditApi().record_security_event(
            conn,
            SecurityEventInput(
                event_type="access.sensitive_read",
                target_ref="inspection:42",
                detail={"fields": ["rates"], "api_token": "abc"},
            ),
        )
    await dispatch_all(outbox)
    [row] = await security_rows(outbox)
    assert (row["event_type"], row["target_ref"], row["actor_id"]) == (
        "access.sensitive_read",
        "inspection:42",
        ALICE_ID,
    )
    assert row["detail"] == {"fields": ["rates"], "api_token": "[redacted]"}
    assert await audit_rows(outbox) == []


async def test_expect_audited_finds_the_entry_and_explains_a_miss(outbox: Outbox) -> None:
    record = uuid4()
    await emit_events(
        outbox, "project.updated", [{"after": {"n": 1}}], aggregate=Aggregate("project", record)
    )
    await dispatch_all(outbox)
    async with with_tenant(TENANT_A_ID, engine=outbox.app) as conn:
        await expect_audited(conn, "project.updated", record_id=record)
        with pytest.raises(AssertionError, match=r"project\.created"):
            await expect_audited(conn, "project.created", record_id=record)


async def test_append_refuses_the_security_stream() -> None:
    with pytest.raises(ValueError, match="record_security_event"):
        await AuditApi().append(TENANT_A_ID, [], stream="security")


def test_record_security_event_refuses_identity_types_and_bad_ips() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SecurityEventInput(event_type="auth.login.succeeded")
    with pytest.raises(ValidationError):
        SecurityEventInput(event_type="access.sensitive_read", source_ip="nope")


async def test_a_late_retry_never_reopens_an_earlier_segment(outbox: Outbox) -> None:
    from datetime import UTC, datetime

    from aip.modules.audit.repository import append_audit_entries
    from aip.modules.audit.schemas import AuditEntryIn
    from aip.platform.db.session import audit_writer_tenant

    def entry(month: int) -> AuditEntryIn:
        return AuditEntryIn(
            event_type="widget.created", occurred_at=datetime(2026, month, 15, tzinfo=UTC)
        )

    async with audit_writer_tenant(TENANT_A_ID) as conn:
        await append_audit_entries(conn, TENANT_A_ID, "audit", [entry(10)])
    async with audit_writer_tenant(TENANT_A_ID) as conn:  # an outbox retry of a September event
        await append_audit_entries(conn, TENANT_A_ID, "audit", [entry(9)])
    rows = await su(
        outbox,
        "SELECT segment, last_seq FROM audit_chain_checkpoints"
        " WHERE tenant_id = $1 ORDER BY segment",
        TENANT_A_ID,
    )
    assert rows == [("2026-10", 2)]
