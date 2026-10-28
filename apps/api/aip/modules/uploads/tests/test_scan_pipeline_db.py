"""Integration tests for the scan pipeline (UPLOADS-02): real Postgres, a real object store and a
local stub clamd (no ClamAV container needed — the clamd client has its own protocol unit tests).

Each test drives the real upload path (create -> presigned POST -> confirm) so a genuine quarantine
object exists, then runs ``run_scan_pipeline`` in a tenant transaction the way the worker does, and
asserts the released/rejected outcome, the append-only ``scan_results`` trail and the emitted event.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import zipfile
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from tests.conftest import ALICE_ID, PROJECT_A1_ID, TENANT_A_ID

from aip.modules.uploads.pipeline.clamav_client import ClamdSettings
from aip.modules.uploads.pipeline.runner import ScanError, run_scan_pipeline
from aip.platform.capabilities import ObjectNotFoundError, get_object_store
from aip.platform.capabilities.keys import ObjectKey
from aip.platform.context import RequestContext, new_request_id, run_with_context
from aip.platform.db.scope import run_as_system

from .conftest import ALICE, BOB, CAROL, StoreCtx, TenantDb, su_execute, su_fetch

# A tenant-scoped role assignment makes ALICE see every project's files (ACCESS-03): the files-url
# route runs as the user, so without scope the row is invisible under the project-scope RLS.
_ROLE_ID = "00000000-0000-4000-8000-00000000a550"


async def _grant_alice_tenant_scope(db: TenantDb) -> None:
    await su_execute(
        db,
        "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
        f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active') "
        "ON CONFLICT DO NOTHING;"
        "INSERT INTO role (id, tenant_id, code, name) VALUES "
        f"('{_ROLE_ID}', '{TENANT_A_ID}', 'uploads_test', 'Uploads Test') ON CONFLICT DO NOTHING;"
        "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type, project_id, "
        f"valid_to) VALUES (gen_random_uuid(), '{TENANT_A_ID}', '{ALICE_ID}', '{_ROLE_ID}', "
        "'tenant', NULL, NULL)",
    )


_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _body(content: bytes, mime: str = "application/pdf") -> dict[str, object]:
    return {
        "projectId": str(PROJECT_A1_ID),
        "filename": "doc.pdf",
        "declaredMime": mime,
        "sizeBytes": len(content),
    }


async def _post_form(url: str, fields: dict[str, str], content: bytes) -> httpx.Response:
    async with httpx.AsyncClient() as hc:
        return await hc.post(url, data=fields, files={"file": ("doc", content)})


async def _upload_and_confirm(
    client: httpx.AsyncClient, content: bytes, *, mime: str = "application/pdf"
) -> UUID:
    """Create a session, drop the bytes in quarantine and confirm; return the session id."""
    created = await client.post(
        "/api/v1/uploads/sessions", json=_body(content, mime), headers=ALICE
    )
    assert created.status_code == 201, created.text
    out = created.json()
    posted = await _post_form(out["url"], out["fields"], content)
    assert posted.status_code == 204, posted.text
    confirmed = await client.post(
        f"/api/v1/uploads/sessions/{out['sessionId']}/confirm", headers=ALICE
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "uploaded"
    return UUID(out["sessionId"])


@contextlib.asynccontextmanager
async def _clamd(verdict: str | None) -> AsyncIterator[ClamdSettings]:
    """A stub clamd: ``"clean"`` -> OK, ``"eicar"`` -> FOUND, ``None`` -> hang (times out)."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with contextlib.suppress(Exception):
            command = await reader.readuntil(b"\x00")
            if command.startswith(b"zVERSION"):
                writer.write(b"ClamAV 1.4.0/27000/stub\x00")
                await writer.drain()
            else:  # zINSTREAM: consume the chunk framing, then answer (or hang)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(reader.read(1 << 20), 0.5)
                if verdict is None:
                    await asyncio.sleep(30)
                else:
                    found = verdict == "eicar"
                    reply = (
                        b"stream: Eicar-Test-Signature FOUND\x00" if found else b"stream: OK\x00"
                    )
                    writer.write(reply)
                    await writer.drain()
        with contextlib.suppress(Exception):
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield ClamdSettings(host="127.0.0.1", port=port, timeout_s=2.0)
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()


async def _run_pipeline(
    db: TenantDb, session_id: UUID, clamd: ClamdSettings, *, is_last_attempt: bool = False
) -> str:
    """Run the pipeline exactly as the worker does: in a tenant tx, within a request context."""

    async def _inner() -> str:
        async with db.with_tenant(TENANT_A_ID) as conn:
            return await run_scan_pipeline(
                conn, session_id, is_last_attempt=is_last_attempt, clamd=clamd
            )

    ctx = RequestContext(
        tenant_id=TENANT_A_ID,
        request_id=new_request_id(),
        project_id=PROJECT_A1_ID,
        actor_id=ALICE_ID,
    )
    return await run_with_context(ctx, _inner)


async def _events(db: TenantDb, session_id: UUID, name: str) -> int:
    rows = await su_fetch(
        db,
        "SELECT count(*) FROM domain_events WHERE event_name = $1 AND aggregate_id = $2",
        name,
        session_id,
    )
    return int(str(rows[0][0]))


async def test_clean_object_is_released_with_a_full_pass_trail(
    client: httpx.AsyncClient, db: TenantDb, store: StoreCtx
) -> None:
    session_id = await _upload_and_confirm(client, _PDF)
    quarantine = await su_fetch(
        db, "SELECT quarantine_key FROM upload_sessions WHERE id = $1", session_id
    )
    quarantine_key = str(quarantine[0][0])

    async with _clamd("clean") as clamd:
        result = await _run_pipeline(db, session_id, clamd)
    assert result.startswith("released:"), result

    session = await su_fetch(
        db, "SELECT status, file_id::text FROM upload_sessions WHERE id = $1", session_id
    )
    assert session[0][0] == "released"
    file_id = session[0][1]

    files = await su_fetch(
        db,
        "SELECT scan_status, detected_mime, size_bytes, sha256, storage_key FROM stored_files "
        "WHERE id = $1",
        UUID(str(file_id)),
    )
    assert len(files) == 1
    scan_status, detected_mime, size_bytes, sha256, storage_key = files[0]
    assert scan_status == "clean"
    assert detected_mime == "application/pdf"
    assert int(str(size_bytes)) == len(_PDF)
    assert sha256 == hashlib.sha256(_PDF).hexdigest()
    assert str(storage_key).startswith(f"tenant/{TENANT_A_ID}/files/")

    stages = await su_fetch(
        db,
        "SELECT stage, outcome FROM scan_results WHERE session_id = $1 ORDER BY created_at",
        session_id,
    )
    assert [(s, o) for s, o in stages] == [
        ("size_cap", "pass"),
        ("magic_bytes", "pass"),
        ("ratio_cap", "pass"),
        ("clamav", "pass"),
    ]
    assert await _events(db, session_id, "upload.completed") == 1

    # The quarantine object is dropped once the clean copy is stored; the released one is readable.
    store_obj = get_object_store()
    with pytest.raises(ObjectNotFoundError):
        await store_obj.head(ObjectKey(quarantine_key))
    assert await store_obj.get(ObjectKey(str(storage_key))) == _PDF


async def test_infected_object_is_rejected_and_nothing_is_released(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    session_id = await _upload_and_confirm(client, _PDF)
    async with _clamd("eicar") as clamd:
        result = await _run_pipeline(db, session_id, clamd)
    assert result == "rejected:clamav", result

    session = await su_fetch(
        db, "SELECT status, reject_reason FROM upload_sessions WHERE id = $1", session_id
    )
    assert session[0] == ("rejected", "clamav")
    clam = await su_fetch(
        db,
        "SELECT outcome, detail->>'signature' FROM scan_results "
        "WHERE session_id = $1 AND stage = 'clamav'",
        session_id,
    )
    assert clam[0][0] == "fail"
    assert "Eicar" in str(clam[0][1])
    assert await _events(db, session_id, "upload.rejected") == 1
    stored = await su_fetch(
        db, "SELECT count(*) FROM stored_files WHERE project_id = $1", PROJECT_A1_ID
    )
    assert int(str(stored[0][0])) == 0


async def test_bytes_that_belie_the_declared_type_are_rejected_at_magic_bytes(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    # Declared application/pdf, but the bytes are HTML: magic bytes rejects before clamd is reached.
    html = b"<html><body>not a pdf</body></html>\n"
    session_id = await _upload_and_confirm(client, html)
    async with _clamd("clean") as clamd:
        result = await _run_pipeline(db, session_id, clamd)
    assert result == "rejected:magic_bytes", result
    stages = await su_fetch(
        db, "SELECT stage FROM scan_results WHERE session_id = $1 ORDER BY created_at", session_id
    )
    assert [s for (s,) in stages] == ["size_cap", "magic_bytes"]  # clamav never ran
    assert await _events(db, session_id, "upload.rejected") == 1


async def test_a_scan_that_cannot_complete_fails_closed_then_rejects_on_the_last_attempt(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    session_id = await _upload_and_confirm(client, _PDF)
    # clamd that accepts VERSION but never answers INSTREAM -> the stage errors (fail-closed).
    async with _clamd(None) as clamd:
        with pytest.raises(ScanError):
            await _run_pipeline(db, session_id, clamd, is_last_attempt=False)
        # The error attempt rolled back; nothing released and no half-written trail persisted.
        rows = await su_fetch(
            db, "SELECT count(*) FROM stored_files WHERE project_id = $1", PROJECT_A1_ID
        )
        assert int(str(rows[0][0])) == 0
        result = await _run_pipeline(db, session_id, clamd, is_last_attempt=True)
    assert result == "rejected:scan_error", result
    session = await su_fetch(
        db, "SELECT status, reject_reason FROM upload_sessions WHERE id = $1", session_id
    )
    assert session[0] == ("rejected", "scan_error")
    assert await _events(db, session_id, "upload.rejected") == 1


async def test_a_redelivered_scan_releases_exactly_once(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    session_id = await _upload_and_confirm(client, _PDF)
    async with _clamd("clean") as clamd:
        first = await _run_pipeline(db, session_id, clamd)
        second = await _run_pipeline(db, session_id, clamd)  # a second delivery of the same job
    assert first.startswith("released:")
    assert second == "noop:released", second
    rows = await su_fetch(
        db, "SELECT count(*) FROM stored_files WHERE project_id = $1", PROJECT_A1_ID
    )
    assert int(str(rows[0][0])) == 1


async def test_scan_results_cannot_be_altered_by_the_app_role(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    session_id = await _upload_and_confirm(client, _PDF)
    async with _clamd("eicar") as clamd:
        await _run_pipeline(db, session_id, clamd)
    # The append-only REVOKE: aip_app may read and insert but never update recorded evidence.
    with pytest.raises(Exception, match="permission denied"):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await conn.execute(
                text("UPDATE scan_results SET outcome = 'pass' WHERE session_id = :sid"),
                {"sid": str(session_id)},
            )


async def test_released_file_download_url_serves_only_the_clean_file(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _grant_alice_tenant_scope(db)
    session_id = await _upload_and_confirm(client, _PDF)
    async with _clamd("clean") as clamd:
        await _run_pipeline(db, session_id, clamd)
    file_id = str(
        (await su_fetch(db, "SELECT file_id::text FROM upload_sessions WHERE id = $1", session_id))[
            0
        ][0]
    )

    ok = await client.get(f"/api/v1/uploads/files/{file_id}/url", headers=ALICE)
    assert ok.status_code == 200, ok.text
    async with httpx.AsyncClient() as hc:
        got = await hc.get(ok.json()["url"])
    assert got.status_code == 200
    assert hashlib.sha256(got.content).hexdigest() == hashlib.sha256(_PDF).hexdigest()

    # Tenant B cannot see the file at all (RLS -> 404), and a tenant-A user without uploads.view
    # (Carol holds only uploads.admin) is told 404 too, so the file's existence is never leaked.
    assert (
        await client.get(f"/api/v1/uploads/files/{file_id}/url", headers=BOB)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/uploads/files/{file_id}/url", headers=CAROL)
    ).status_code == 404


async def test_file_url_is_409_while_a_file_is_not_released(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _grant_alice_tenant_scope(db)
    # Seed a non-clean stored_files row as the system principal (a quarantined file is never
    # released); the project-scope RLS WITH CHECK fails closed without a principal.
    file_id = uuid4()
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        await conn.execute(
            text(
                "INSERT INTO stored_files (id, tenant_id, project_id, uploaded_by, scan_status, "
                "preview_status, detected_mime, size_bytes, sha256, storage_key) VALUES "
                "(:id, :t, :p, :u, 'quarantined', 'none', 'application/pdf', 3, '00', "
                "'tenant/x/files/x')"
            ),
            {
                "id": str(file_id),
                "t": str(TENANT_A_ID),
                "p": str(PROJECT_A1_ID),
                "u": str(ALICE_ID),
            },
        )
    resp = await client.get(f"/api/v1/uploads/files/{file_id}/url", headers=ALICE)
    assert resp.status_code == 409
    assert resp.json()["code"] == "NOT_RELEASED"


def _xlsx() -> bytes:
    """A minimal OOXML workbook container (enough for magic bytes and the zip caps)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook/>')
        zf.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet/>')
    return buf.getvalue()


@pytest.mark.parametrize(
    ("content", "mime"),
    [
        ("﻿Tag Number,Name,Rating
KF-01,Pump,1.5
".encode(), "text/csv"),
        (_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ],
)
async def test_csv_and_xlsx_imports_are_released_with_their_type_and_file_id(
    client: httpx.AsyncClient, db: TenantDb, content: bytes, mime: str
) -> None:
    # UPLOADS-08: data_io reads these; a CSV must keep ``text/csv`` (not ``text/plain``), and the
    # session status names the released file.
    session_id = await _upload_and_confirm(client, content, mime=mime)
    async with _clamd("clean") as clamd:
        result = await _run_pipeline(db, session_id, clamd)
    assert result.startswith("released:"), result

    rows = await su_fetch(
        db,
        "SELECT f.id, f.detected_mime, f.filename, f.source FROM stored_files f "
        "JOIN upload_sessions s ON s.file_id = f.id WHERE s.id = $1",
        session_id,
    )
    assert len(rows) == 1
    file_id, detected_mime, filename, source = rows[0]
    assert (detected_mime, filename, source) == (mime, "doc.pdf", "upload")

    status = await client.get(f"/api/v1/uploads/sessions/{session_id}/status", headers=ALICE)
    assert status.status_code == 200, status.text
    assert status.json() == {"status": "released", "rejectReason": None, "fileId": str(file_id)}
