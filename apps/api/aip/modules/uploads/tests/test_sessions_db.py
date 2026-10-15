"""Integration tests for upload sessions (UPLOADS-01).

Real Postgres (Testcontainers) and a real S3-compatible store (RustFS). The presigned POST is sent
to the store exactly as a browser would, so the store itself — not the app — is what refuses an
oversized object, a wrong content type or a different key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from tests.conftest import ALICE_ID, PROJECT_A1_ID, TENANT_A_ID

from aip.modules.uploads.service import UploadSessionService
from aip.platform.context import RequestContext, new_request_id, run_with_context

from .conftest import ALICE, BOB, CAROL, PROJECT_A2_ID, StoreCtx, TenantDb, su_fetch


def _body(size: int = 1024, mime: str = "image/jpeg", **extra: Any) -> dict[str, Any]:
    return {
        "projectId": str(PROJECT_A1_ID),
        "filename": "photo.jpg",
        "declaredMime": mime,
        "sizeBytes": size,
        **extra,
    }


async def _post_form(url: str, fields: dict[str, str], content: bytes) -> httpx.Response:
    """Send the presigned browser POST to the store, with the file part last (as S3 requires)."""
    async with httpx.AsyncClient() as hc:
        return await hc.post(url, data=fields, files={"file": ("photo.jpg", content)})


async def test_create_upload_confirm_round_trip(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    assert created.status_code == 201, created.text
    out = created.json()
    assert UUID(out["sessionId"])
    assert out["expiresAt"]

    posted = await _post_form(out["url"], out["fields"], b"\xff\xd8\xff" + b"0" * 1021)
    assert posted.status_code == 204, posted.text

    confirmed = await client.post(
        f"/api/v1/uploads/sessions/{out['sessionId']}/confirm", headers=ALICE
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "uploaded"


async def test_quarantine_key_is_tenant_prefixed_and_opaque(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    out = created.json()
    rows = await su_fetch(
        db, "SELECT quarantine_key FROM upload_sessions WHERE id = $1", UUID(out["sessionId"])
    )
    key = str(rows[0][0])
    assert key.startswith(f"tenant/{TENANT_A_ID}/quarantine/")
    assert "photo.jpg" not in key and out["sessionId"] not in key


async def test_oversized_object_is_refused_and_confirm_is_object_missing(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    out = created.json()
    # The policy pins content-length-range [1, 1024]; 2048 bytes is EntityTooLarge.
    posted = await _post_form(out["url"], out["fields"], b"0" * 2048)
    assert posted.status_code in (400, 403), posted.text
    confirmed = await client.post(
        f"/api/v1/uploads/sessions/{out['sessionId']}/confirm", headers=ALICE
    )
    assert confirmed.status_code == 409
    assert confirmed.json()["code"] == "OBJECT_MISSING"


async def test_wrong_content_type_is_refused_by_store(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    out = created.json()
    tampered = {**out["fields"], "Content-Type": "text/html"}
    posted = await _post_form(out["url"], tampered, b"0" * 1024)
    assert posted.status_code in (400, 403), posted.text


async def test_tampered_key_is_refused_by_store(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    out = created.json()
    tampered = {**out["fields"], "key": f"tenant/{TENANT_A_ID}/quarantine/other"}
    posted = await _post_form(out["url"], tampered, b"0" * 1024)
    assert posted.status_code in (400, 403), posted.text


async def test_another_user_cannot_confirm_and_existence_is_not_leaked(
    client: httpx.AsyncClient,
) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    session_id = created.json()["sessionId"]
    # Carol (same tenant) is not the requester: 404, not 403, so the session is not revealed.
    carol = await client.post(f"/api/v1/uploads/sessions/{session_id}/confirm", headers=CAROL)
    assert carol.status_code == 404
    # Bob (tenant B) cannot even see its status.
    bob = await client.get(f"/api/v1/uploads/sessions/{session_id}/status", headers=BOB)
    assert bob.status_code == 404


async def test_admin_may_read_status(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    session_id = created.json()["sessionId"]
    # Carol holds uploads.admin on P1 (the session's project).
    status = await client.get(f"/api/v1/uploads/sessions/{session_id}/status", headers=CAROL)
    assert status.status_code == 200
    assert status.json()["status"] == "requested"


async def test_create_without_permission_on_project_is_forbidden(
    client: httpx.AsyncClient,
) -> None:
    body = {**_body(1024), "projectId": str(PROJECT_A2_ID)}
    created = await client.post("/api/v1/uploads/sessions", json=body, headers=ALICE)
    assert created.status_code == 403


async def test_repeated_client_request_id_is_idempotent(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    crid = "00000000-0000-4000-8000-0000000c0d01"
    body = _body(1024, clientRequestId=crid)
    first = await client.post("/api/v1/uploads/sessions", json=body, headers=ALICE)
    second = await client.post("/api/v1/uploads/sessions", json=body, headers=ALICE)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["sessionId"] == second.json()["sessionId"]
    rows = await su_fetch(
        db, "SELECT count(*) FROM upload_sessions WHERE client_request_id = $1", UUID(crid)
    )
    assert rows[0][0] == 1


async def test_stale_session_expires_and_confirm_conflicts(
    client: httpx.AsyncClient, store: StoreCtx
) -> None:
    created = await client.post("/api/v1/uploads/sessions", json=_body(1024), headers=ALICE)
    session_id = created.json()["sessionId"]

    ctx = RequestContext(tenant_id=TENANT_A_ID, request_id=new_request_id(), actor_id=ALICE_ID)
    expired = await run_with_context(
        ctx,
        UploadSessionService().expire_stale_sessions,
        datetime.now(UTC) + timedelta(minutes=16),
    )
    assert expired == 1

    confirmed = await client.post(f"/api/v1/uploads/sessions/{session_id}/confirm", headers=ALICE)
    assert confirmed.status_code == 409
