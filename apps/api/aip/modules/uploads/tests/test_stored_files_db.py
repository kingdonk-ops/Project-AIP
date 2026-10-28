"""Integration tests for server-side file access (UPLOADS-08): real Postgres and a real object store.

Each test calls the published interface the way a worker does: on a ``run_as_system`` connection
for the job's tenant. The ``client`` fixture is requested for its environment (object-store
settings and the app engine); nothing here goes through HTTP.
"""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from tests.conftest import ALICE_ID, PROJECT_A1_ID, TENANT_A_ID, TENANT_B_ID

from aip.modules.uploads.api import (
    StoredFileConflict,
    StoredFileIntegrityError,
    StoredFileNotFound,
    get_stored_file,
    open_stored_file,
    store_generated_file,
)
from aip.platform.capabilities import get_object_store
from aip.platform.capabilities.keys import ObjectKey
from aip.platform.db.scope import run_as_system

from .conftest import TenantDb, su_execute, su_fetch

_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
_PDF_B = _PDF.replace(b"1 0 obj", b"2 0 obj")
_KEY = "report-render:1"

pytestmark = pytest.mark.usefixtures("client")


class _Rollback(Exception):
    pass


async def _store(db: TenantDb, data: bytes = _PDF, key: str = _KEY) -> UUID:
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        ref = await store_generated_file(
            conn,
            data=data,
            filename="project-summary-internal-KF-01.pdf",
            content_type="application/pdf",
            purpose="report",
            idempotency_key=key,
            project_id=PROJECT_A1_ID,
        )
    return ref.id


async def _count(db: TenantDb) -> int:
    rows = await su_fetch(db, "SELECT count(*) FROM stored_files")
    return int(str(rows[0][0]))


async def test_a_generated_file_is_stored_clean_and_reads_back(db: TenantDb) -> None:
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        ref = await store_generated_file(
            conn,
            data=_PDF,
            filename="summary.pdf",
            content_type="application/pdf",
            purpose="report",
            idempotency_key=_KEY,
            project_id=PROJECT_A1_ID,
        )
    assert ref.sha256 == hashlib.sha256(_PDF).hexdigest()
    assert ref.size_bytes == len(_PDF)
    assert (ref.source, ref.purpose, ref.filename) == ("generated", "report", "summary.pdf")

    rows = await su_fetch(
        db,
        "SELECT source, scan_status, storage_key, uploaded_by FROM stored_files WHERE id = $1",
        ref.id,
    )
    assert len(rows) == 1
    source, scan_status, storage_key, uploaded_by = rows[0]
    assert (source, scan_status, uploaded_by) == ("generated", "clean", None)
    assert str(storage_key) == f"tenant/{TENANT_A_ID}/files/{ref.id}"

    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        assert await get_stored_file(conn, ref.id) == ref
        assert await open_stored_file(conn, ref.id) == _PDF


async def test_a_tenant_level_file_needs_no_project(db: TenantDb) -> None:
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        ref = await store_generated_file(
            conn,
            data=b"a,b\n1,2\n",
            filename="errors.csv",
            content_type="text/csv",
            purpose="export",
            idempotency_key="export:1",
            created_by=ALICE_ID,
        )
    assert ref.project_id is None
    assert ref.content_type == "text/csv"


async def test_the_same_key_replays_and_different_bytes_conflict(db: TenantDb) -> None:
    first = await _store(db)
    assert await _store(db) == first
    assert await _count(db) == 1
    with pytest.raises(StoredFileConflict):
        await _store(db, _PDF_B)
    assert await _count(db) == 1


async def test_a_rolled_back_attempt_leaves_no_orphan_object(db: TenantDb) -> None:
    # The first attempt stores the object, then the job's transaction rolls back.
    with pytest.raises(_Rollback):
        async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
            await store_generated_file(
                conn,
                data=_PDF,
                filename="r.pdf",
                content_type="application/pdf",
                purpose="report",
                idempotency_key=_KEY,
            )
            raise _Rollback
    assert await _count(db) == 0

    # The retry renders slightly different bytes; it writes the same key, so nothing is orphaned.
    retried = await _store(db, _PDF_B)
    assert await _count(db) == 1
    key = ObjectKey(f"tenant/{TENANT_A_ID}/files/{retried}")
    assert await get_object_store().get(key) == _PDF_B


async def test_only_clean_live_files_of_the_tenant_are_visible(db: TenantDb) -> None:
    file_id = await _store(db)

    # Another tenant sees nothing.
    async with run_as_system(TENANT_B_ID, engine=db.engine) as conn:
        assert await get_stored_file(conn, file_id) is None
        with pytest.raises(StoredFileNotFound):
            await open_stored_file(conn, file_id)

    # A file that is not clean is invisible too.
    quarantined = uuid4()
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        await conn.execute(
            text(
                "INSERT INTO stored_files (id, tenant_id, project_id, uploaded_by, scan_status, "
                "preview_status, detected_mime, size_bytes, sha256, storage_key) VALUES "
                "(:id, :t, :p, :u, 'quarantined', 'none', 'application/pdf', 3, '00', "
                "'tenant/x/files/x')"
            ),
            {
                "id": str(quarantined),
                "t": str(TENANT_A_ID),
                "p": str(PROJECT_A1_ID),
                "u": str(ALICE_ID),
            },
        )
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        assert await get_stored_file(conn, quarantined) is None
        with pytest.raises(StoredFileNotFound):
            await open_stored_file(conn, quarantined)

    # So is a soft-deleted one.
    await su_execute(db, f"UPDATE stored_files SET deleted_at = now() WHERE id = '{file_id}'")
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        assert await get_stored_file(conn, file_id) is None
        with pytest.raises(StoredFileNotFound):
            await open_stored_file(conn, file_id)


async def test_bytes_altered_behind_the_row_are_refused(db: TenantDb) -> None:
    file_id = await _store(db)
    key = ObjectKey(f"tenant/{TENANT_A_ID}/files/{file_id}")
    await get_object_store().put(key, _PDF_B, content_type="application/pdf")
    async with run_as_system(TENANT_A_ID, engine=db.engine) as conn:
        with pytest.raises(StoredFileIntegrityError):
            await open_stored_file(conn, file_id)


async def test_without_a_principal_the_store_is_refused(db: TenantDb) -> None:
    with pytest.raises(Exception, match="row-level security"):
        async with db.with_tenant(TENANT_A_ID) as conn:
            await store_generated_file(
                conn,
                data=_PDF,
                filename="r.pdf",
                content_type="application/pdf",
                purpose="report",
                idempotency_key=_KEY,
                project_id=PROJECT_A1_ID,
            )
    assert await _count(db) == 0

