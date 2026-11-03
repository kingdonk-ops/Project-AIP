"""REPORTS-03 integration tests: approving an inspection renders its internal and client reports.

Real Postgres (``aip_app``, RLS on), the RustFS object store and, for the end-to-end render,
Gotenberg (the STACK-02 fixtures; in CI the compose stack's). An inspection of FORMS-01's
``coating-itr-min`` form on asset ``P-1001`` is driven through the APPROVALS-09 v2
``inspection_standard`` preset: ``ready`` (supervisor) → ``inspect`` (inspector) → answers →
``request_supervisor_review`` (inspector) → ``mark_performed`` (supervisor, a fresh aal 2 session).
``performed`` is the approved, terminal state (ADR 0041 renamed v1's ``completed``). The outbox is
dispatched in-process with the inspections and report_engine subscribers, and the ``pdf`` queue is
drained in-process as in REPORTS-02.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import struct
import sys
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from pypdf import PdfReader
from sqlalchemy import text
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixture
    Outbox,
    TenantDb,
    outbox,  # pyright: ignore[reportUnusedImport]
)

from aip.modules.approvals.api import ApprovalsApi
from aip.modules.assets.api import AssetCreate, AssetsApi
from aip.modules.report_engine.events import render_on_inspection_state_changed
from aip.modules.report_engine.loader import run
from aip.modules.report_engine.providers import inspection as inspection_provider
from aip.modules.report_engine.template_package import load_package
from aip.modules.uploads.api import open_stored_file, store_generated_file
from aip.platform.context import RequestContext, use_context
from aip.platform.db.migrator import repo_root
from aip.platform.db.scope import run_as_system
from aip.platform.events.dispatcher import DispatchSettings, dispatch_batch
from aip.platform.events.subscribers import (
    DomainEvent,
    SubscriberRegistry,
    subscribers,
)

from .conftest import (
    ALICE,
    BOB,
    CAROL,
    CAROL_ID,
    ROLE_A_ID,
    GrantTable,
    RenderEnv,
    add_project,
    ctx,
    stub_headers,
    su_execute,
    su_fetch,
)
from .test_render_pdf import drain

INSPECTIONS = "/api/v1/inspections"
RENDERS = "/api/v1/reports/renders"
TEMPLATES = "/api/v1/reports/templates"
ROOT = repo_root() / "config" / "report-templates"
COATING = json.loads(
    (repo_root() / "apps/api/aip/modules/forms/tests/fixtures/coating-itr-min.json").read_text(
        "utf-8"
    )
)

SUPERVISOR_ID = UUID("00000000-0000-4000-8000-0000000005e1")
INSPECTOR_ID = UUID("00000000-0000-4000-8000-0000000005e2")
INSPECTOR_NAME, SUPERVISOR_NAME = "Ivy Inspector", "Sam Supervisor"
FAIL = "Fail"  # report.inspection.result.fail in en-AU

pytestmark = pytest.mark.usefixtures("scope_users")


def _signed(user: UUID) -> dict[str, str]:
    """A fresh aal 2 (TOTP) session: passes the critical-transition sign-off policy."""
    principal = {
        "kind": "user",
        "tenantId": str(TENANT_A_ID),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": 2,
        "amr": ["pwd", "otp"],
        "authenticatedAt": datetime.now(UTC).isoformat(),
    }
    return {"x-test-principal": json.dumps(principal)}


SUPERVISOR = stub_headers(TENANT_A_ID, SUPERVISOR_ID)
INSPECTOR = stub_headers(TENANT_A_ID, INSPECTOR_ID)
FORMS = {"form.view", "form.manage", "form.publish"}
REPORTS = {"report.view", "report.create", "report.template.view", "report.template.manage"}


@pytest.fixture
async def people(db: TenantDb, scope_users: GrantTable) -> GrantTable:
    """The supervisor and inspector (named as on the report), with the lifecycle grants."""
    await su_execute(
        db,
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status,"
        " mfa_enrolled_at) VALUES "
        f"('{SUPERVISOR_ID}', '{TENANT_A_ID}', 'staff', 'sam@kaefer.test', '{SUPERVISOR_NAME}',"
        " 'active', now()), "
        f"('{INSPECTOR_ID}', '{TENANT_A_ID}', 'staff', 'ivy@kaefer.test', '{INSPECTOR_NAME}',"
        " 'active', NULL);"
        "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type) VALUES "
        f"(gen_random_uuid(), '{TENANT_A_ID}', '{SUPERVISOR_ID}', '{ROLE_A_ID}', 'tenant'), "
        f"(gen_random_uuid(), '{TENANT_A_ID}', '{INSPECTOR_ID}', '{ROLE_A_ID}', 'tenant')",
    )
    grants = scope_users
    grants.by_user[ALICE_ID] |= {*FORMS, *REPORTS, "inspection.view", "asset.view"}
    grants.by_user[SUPERVISOR_ID] = {
        "inspection.view",
        "inspection.create",
        "approvals.view",
        "approvals.inspection.assign",
        "approvals.inspection.approve",
    }
    grants.by_user[INSPECTOR_ID] = {
        "inspection.view",
        "inspection.respond",
        "approvals.view",
        "approvals.inspection.execute",
    }
    return grants


@dataclass(frozen=True)
class World:
    project_id: UUID
    asset_id: UUID
    form_id: str


async def _load(tenants: tuple[UUID, ...] = (TENANT_A_ID,)) -> None:
    out, err = io.StringIO(), io.StringIO()
    assert await run(ROOT, tenants, out=out, err=err) == 0, err.getvalue()


async def _load_terms(db: TenantDb) -> None:
    """The en-AU dictionary, loaded as the deploy migrate job does (``terms.loader``)."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "aip.modules.terms.loader",
        str(repo_root() / "config" / "terms" / "en-AU"),
        env={**os.environ, "DATABASE_MIGRATOR_URL": db.db.owner_url},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await process.communicate()
    assert process.returncode == 0, err.decode()


async def _world(client: httpx.AsyncClient, db: TenantDb) -> World:
    """The en-AU dictionary, the report templates (tenant A only), project KF-01, the preset,
    asset P-1001 and the form."""
    await _load_terms(db)
    await _load()
    project_id = await add_project(db)
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await ApprovalsApi().install_preset(conn, "inspection_standard")
            asset = await AssetsApi().create_asset(
                conn, ALICE_ID, AssetCreate(name="Process line P-1001", tag_number="P-1001")
            )
    body = {"code": "coating-itr-min", "name": "Coating ITR", "kind": "inspection"}
    uploaded = await client.post(
        "/api/v1/forms/templates", json={**body, "schema": COATING}, headers=ALICE
    )
    assert uploaded.status_code == 201, uploaded.text
    revision_id = uploaded.json()["revision"]["id"]
    published = await client.post(
        f"/api/v1/forms/revisions/{revision_id}/publish", json={}, headers=ALICE
    )
    assert published.status_code == 200, published.text
    return World(project_id, asset.id, uploaded.json()["template"]["id"])


def _png(rgb: tuple[int, int, int], width: int = 48, height: int = 32) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


async def _photos(db: TenantDb, world: World) -> list[str]:
    ids: list[str] = []
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        for n, colour in enumerate(((200, 40, 40), (40, 120, 200))):
            ref = await store_generated_file(
                conn,
                data=_png(colour),
                filename=f"coating-{n}.png",
                content_type="image/png",
                purpose="inspection-photo",
                idempotency_key=f"test-photo:{uuid.uuid4()}",
                project_id=world.project_id,
            )
            ids.append(str(ref.id))
    return ids


async def _move(client: httpx.AsyncClient, inspection_id: str, action: str, user: UUID) -> None:
    response = await client.post(
        f"{INSPECTIONS}/{inspection_id}/transition",
        json={"action": action},
        headers=_signed(user),
    )
    assert response.status_code == 200, (action, response.text)


async def _inspection_for_review(
    client: httpx.AsyncClient, world: World, photos: list[str] | None = None
) -> str:
    """A new inspection, answered (``dft_avg`` 0.2 mm fails), waiting in ``supervisor_review``."""
    created = await client.post(
        INSPECTIONS,
        json={
            "assetId": str(world.asset_id),
            "projectId": str(world.project_id),
            "templateId": world.form_id,
            "kind": "inspection",
        },
        headers=SUPERVISOR,
    )
    assert created.status_code == 201, created.text
    inspection_id: str = created.json()["id"]
    await _move(client, inspection_id, "ready", SUPERVISOR_ID)
    await _move(client, inspection_id, "inspect", INSPECTOR_ID)
    answers: list[dict[str, Any]] = [
        {"fieldKey": "surface_prepared", "value": True},
        {"fieldKey": "blast_standard", "value": "sa2_5"},
        {"fieldKey": "dft_avg", "value": {"value": 0.2, "unit": "mm"}},
    ]
    if photos:
        answers.append({"fieldKey": "photos", "value": [{"fileId": f} for f in photos]})
    answered = await client.post(
        f"{INSPECTIONS}/{inspection_id}/responses",
        json={"answers": [{**a, "clientId": str(uuid.uuid4())} for a in answers]},
        headers=INSPECTOR,
    )
    assert answered.status_code == 200, answered.text
    await _move(client, inspection_id, "request_supervisor_review", INSPECTOR_ID)
    return inspection_id


def _registry(*extra: tuple[str, Callable[..., Any]]) -> SubscriberRegistry:
    registry = subscribers.for_modules(["inspections", "report_engine"])
    for event_name, handler in extra:
        registry.register(event_name, 1, handler, owner="test")
    return registry


async def _dispatch(box: Outbox, registry: SubscriberRegistry | None = None) -> None:
    settings = DispatchSettings(batch_size=100)
    chosen = registry or _registry()
    while (await dispatch_batch(box.jobs, box.app, chosen, settings)).claimed:
        pass


async def _jobs(db: TenantDb, inspection_id: str) -> list[dict[str, Any]]:
    rows = await su_fetch(
        db,
        "SELECT id, variant, status, trigger_event_id, requested_by, snapshot_id, file_id,"
        " pdf_sha256 FROM report_render_jobs WHERE record_id = $1 ORDER BY variant",
        UUID(inspection_id),
    )
    keys = (
        "id",
        "variant",
        "status",
        "trigger_event_id",
        "requested_by",
        "snapshot_id",
        "file_id",
        "pdf_sha256",
    )
    return [dict(zip(keys, row, strict=True)) for row in rows]


async def _count(db: TenantDb, sql: str, *args: object) -> int:
    return int(str((await su_fetch(db, sql, *args))[0][0]))


async def _approved_event(db: TenantDb, inspection_id: str) -> DomainEvent:
    rows = await su_fetch(
        db,
        "SELECT id, tenant_id, project_id, asset_id, event_name, event_version, aggregate_type,"
        " aggregate_id, payload, actor_id, occurred_at, attempts FROM domain_events"
        " WHERE event_name = 'inspection.state_changed' AND aggregate_id = $1"
        " AND payload->>'to' = 'performed'",
        UUID(inspection_id),
    )
    (row,) = rows
    values = dict(zip(DomainEvent.__dataclass_fields__, row, strict=True))
    if isinstance(values["payload"], str):
        values["payload"] = json.loads(values["payload"])
    return DomainEvent(**values)


async def _redeliver(db: TenantDb, event: DomainEvent) -> None:
    context = RequestContext(
        tenant_id=event.tenant_id, request_id=f"replay-{event.id}", actor_id=event.actor_id
    )
    with use_context(context):
        async with run_as_system(event.tenant_id, engine=db.engine) as conn:
            await render_on_inspection_state_changed(conn, event)


async def _pdf(db: TenantDb, file_id: UUID) -> bytes:
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        return await open_stored_file(conn, file_id)


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


async def test_approval_renders_internal_and_client_reports_once(
    app: FastAPI,
    client: httpx.AsyncClient,
    db: TenantDb,
    people: GrantTable,
    render_env: RenderEnv,
    outbox: Outbox,  # noqa: F811
) -> None:
    world = await _world(client, db)
    inspection_id = await _inspection_for_review(client, world, await _photos(db, world))

    await _dispatch(outbox)  # every earlier state change (in_progress included) renders nothing
    assert await _jobs(db, inspection_id) == []

    await _move(client, inspection_id, "mark_performed", SUPERVISOR_ID)
    await _dispatch(outbox)
    event = await _approved_event(db, inspection_id)
    jobs = await _jobs(db, inspection_id)
    assert [(j["variant"], j["status"]) for j in jobs] == [
        ("client", "queued"),
        ("internal", "queued"),
    ]
    assert {j["trigger_event_id"] for j in jobs} == {event.id}
    assert {j["requested_by"] for j in jobs} == {SUPERVISOR_ID}
    snapshots = "SELECT count(*) FROM report_data_snapshots WHERE record_id = $1"
    assert await _count(db, snapshots, UUID(inspection_id)) == 2

    await _redeliver(db, event)  # at-least-once delivery: the same event creates nothing
    assert [j["id"] for j in await _jobs(db, inspection_id)] == [j["id"] for j in jobs]
    assert await _count(db, snapshots, UUID(inspection_id)) == 2

    await drain(db, render_env)
    done = {j["variant"]: j for j in await _jobs(db, inspection_id)}
    assert {v: j["status"] for v, j in done.items()} == {
        "client": "succeeded",
        "internal": "succeeded",
    }
    internal = await _pdf(db, done["internal"]["file_id"])
    client_pdf = await _pdf(db, done["client"]["file_id"])
    for pdf, job in ((internal, done["internal"]), (client_pdf, done["client"])):
        assert len(job["pdf_sha256"]) == 64
        for page in PdfReader(io.BytesIO(pdf)).pages:  # landscape A4: 842 x 595 pt
            assert float(page.mediabox.width) > float(page.mediabox.height)
    internal_text = _pdf_text(internal)
    assert "P-1001" in internal_text and FAIL in internal_text
    assert INSPECTOR_NAME in internal_text and SUPERVISOR_NAME in internal_text
    assert len(PdfReader(io.BytesIO(internal)).pages[0].images) >= 2  # the logo and photos
    client_text = _pdf_text(client_pdf)
    assert "P-1001" in client_text and FAIL in client_text
    assert INSPECTOR_NAME not in client_text
    assert inspection_id not in client_text

    # Tenant B sees none of it.
    other = await client.get(f"{RENDERS}/{done['client']['id']}", headers=BOB)
    assert other.status_code == 404 and other.json()["code"] == "RENDER_JOB_NOT_FOUND"


async def test_a_newer_version_without_auto_render_turns_it_off(
    app: FastAPI,
    client: httpx.AsyncClient,
    db: TenantDb,
    people: GrantTable,
    outbox: Outbox,  # noqa: F811
) -> None:
    world = await _world(client, db)
    package = load_package(ROOT / "inspection" / "client" / "v1")
    definition = {k: v for k, v in package.definition.items() if k != "autoRender"}
    upload = {
        "definition": {**definition, "version": 2},
        "body": package.body,
        "css": package.css,
        "sampleData": dict(package.sample_data),
        "assets": {n: base64.b64encode(a.data).decode() for n, a in package.assets.items()},
    }
    created = await client.post(TEMPLATES, json=upload, headers=ALICE)
    assert created.status_code == 201, created.text
    published = await client.post(f"{TEMPLATES}/{created.json()['id']}/publish", headers=ALICE)
    assert published.status_code == 200, published.text

    inspection_id = await _inspection_for_review(client, world)
    await _move(client, inspection_id, "mark_performed", SUPERVISOR_ID)
    await _dispatch(outbox)
    assert [j["variant"] for j in await _jobs(db, inspection_id)] == ["internal"]


async def test_a_report_failure_never_rolls_back_another_subscriber(
    app: FastAPI,
    client: httpx.AsyncClient,
    db: TenantDb,
    people: GrantTable,
    outbox: Outbox,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    world = await _world(client, db)
    inspection_id = await _inspection_for_review(client, world)
    await _dispatch(outbox)
    await su_execute(
        db, "CREATE TABLE test_markers (event_id uuid); GRANT INSERT ON test_markers TO aip_app"
    )

    async def marker(conn: Any, event: DomainEvent) -> None:
        await conn.execute(text("INSERT INTO test_markers VALUES (:id)"), {"id": event.id})

    async def gone(conn: Any, inspection: UUID) -> None:
        return None

    source = inspection_provider.inspection_source
    monkeypatch.setattr(source, "_deps", replace(source.deps, get_inspection=gone))
    await _move(client, inspection_id, "mark_performed", SUPERVISOR_ID)
    with caplog.at_level(logging.WARNING, logger="aip.modules.report_engine.auto_render"):
        await _dispatch(outbox, _registry(("inspection.state_changed", marker)))

    event = await _approved_event(db, inspection_id)
    markers = await su_fetch(db, "SELECT event_id FROM test_markers")
    assert (event.id,) in markers  # the other subscriber's work committed
    assert await _jobs(db, inspection_id) == []
    logged = [r.getMessage() for r in caplog.records if "auto-render" in r.getMessage()]
    assert any(str(event.id) in m and "RECORD_NOT_FOUND" in m for m in logged), logged
    published = "SELECT published_at IS NOT NULL FROM domain_events WHERE id = $1"
    assert (await su_fetch(db, published, event.id))[0][0] is True


async def test_a_tenant_without_inspection_templates_renders_nothing(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb, people: GrantTable
) -> None:
    await _load((TENANT_A_ID,))  # tenant B gets no report templates
    event = DomainEvent(
        id=uuid.uuid4(),
        tenant_id=TENANT_B_ID,
        project_id=None,
        asset_id=None,
        event_name="inspection.state_changed",
        event_version=1,
        aggregate_type="inspection",
        aggregate_id=uuid.uuid4(),
        payload={
            "inspectionId": str(uuid.uuid4()),
            "assetId": str(uuid.uuid4()),
            "projectId": None,
            "from": "supervisor_review",
            "to": "performed",
            "action": "mark_performed",
        },
        actor_id=BOB_ID,
        occurred_at=datetime.now(UTC),
        attempts=1,
    )
    await _redeliver(db, event)
    count = "SELECT count(*) FROM report_render_jobs WHERE tenant_id = $1"
    assert await _count(db, count, TENANT_B_ID) == 0


async def test_a_manual_render_needs_inspection_view_and_has_no_approval(
    app: FastAPI,
    client: httpx.AsyncClient,
    db: TenantDb,
    people: GrantTable,
) -> None:
    world = await _world(client, db)
    inspection_id = await _inspection_for_review(client, world)
    body = {
        "templateKey": "inspection",
        "variant": "client",
        "recordType": "inspection",
        "recordId": inspection_id,
    }
    people.by_user[CAROL_ID] = {"report.create", "report.view"}  # no inspection.view
    denied = await client.post(RENDERS, json=body, headers=CAROL)
    assert denied.status_code == 403, denied.text
    assert await _jobs(db, inspection_id) == []
    assert await _count(db, "SELECT count(*) FROM report_data_snapshots") == 0

    people.by_user[CAROL_ID] |= {"inspection.view"}
    accepted = await client.post(RENDERS, json=body, headers=CAROL)
    assert accepted.status_code == 202, accepted.text
    rows = await su_fetch(
        db,
        "SELECT s.data FROM report_data_snapshots s JOIN report_render_jobs j"
        " ON j.snapshot_id = s.id WHERE j.id = $1",
        UUID(accepted.json()["id"]),
    )
    data = rows[0][0] if isinstance(rows[0][0], dict) else json.loads(rows[0][0])
    assert data["record"]["approval"] == {}
    assert data["record"]["asset"]["tagNumber"] == "P-1001"
    assert accepted.json()["recordLabel"] == "KF-01 P-1001 Process line P-1001"
