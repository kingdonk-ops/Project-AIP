"""TERMS-07: GET /api/v1/terms/coverage (integration, real Postgres).

The real app is built with ``AUTH_TEST_STUB`` and the real role grants. ``alice`` (kaefer-demo)
holds ``terms.coverage.read`` through a tenant role; ``carol`` (same tenant, no grant) does not.
The findings file is the scanner's output over ``tests/fixtures/lint``, pointed at with
``TERMS_LINT_FINDINGS`` in place of the file the image build bakes in.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.modules.access.api import sync_catalogue
from aip.modules.terms.lint import main as lint_main
from aip.platform.db.engine import dispose_engine

REPO_ROOT = Path(__file__).resolve().parents[6]
FIXTURES = Path(__file__).parent / "fixtures" / "lint"
FIXTURE_DIR = "apps/api/aip/modules/terms/tests/fixtures/lint"
CAROL_ID = UUID("00000000-0000-4000-8000-00000000ca01")  # kaefer-demo user with no grant
TERMS_ROLE_ID = UUID("00000000-0000-4000-8000-0000000007e7")
COMMIT = "0123456789abcdef0123456789abcdef01234567"

SEED_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active');"
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active'), "
    f"('{CAROL_ID}', '{TENANT_A_ID}', 'staff', 'carol@kaefer.test', 'Carol', 'active');"
)
# Run only after sync_catalogue: role_permission.permission_code has an FK to the permission table.
GRANT_SQL = (
    "INSERT INTO role (id, tenant_id, code, name, is_system) VALUES "
    f"('{TERMS_ROLE_ID}', '{TENANT_A_ID}', 'terms_admin', 'Terms Admin', false);"
    "INSERT INTO role_permission (id, tenant_id, role_id, permission_code) VALUES "
    f"(gen_random_uuid(), '{TENANT_A_ID}', '{TERMS_ROLE_ID}', 'terms.coverage.read');"
    "INSERT INTO role_assignment (id, tenant_id, user_id, role_id, scope_type) VALUES "
    f"(gen_random_uuid(), '{TENANT_A_ID}', '{ALICE_ID}', '{TERMS_ROLE_ID}', 'tenant');"
)


def headers(user: UUID) -> dict[str, str]:
    principal = {
        "kind": "user",
        "tenantId": str(TENANT_A_ID),
        "userId": str(user),
        "userClass": "staff",
        "sessionId": None,
        "aal": 2,
        "amr": ["fed"],
    }
    return {"x-test-principal": json.dumps(principal)}


@pytest.fixture
def findings_file(tmp_path: Path) -> Path:
    out = tmp_path / "lint_findings.json"
    lint_main(
        ["--root", str(REPO_ROOT), "--sources", str(FIXTURES), "--out", str(out), "--report-only"]
    )
    return out


@pytest.fixture
async def client(
    tenant_db: TenantDb,  # noqa: F811
    findings_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    await _execute(tenant_db.db.superuser_url, SEED_SQL)
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.setenv("AUTH_TEST_STUB", "1")
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    monkeypatch.setenv("TERMS_LINT_FINDINGS", str(findings_file))
    monkeypatch.setenv("GIT_SHA", COMMIT)
    await dispose_engine()
    app: FastAPI = create_app(env="test", tracing=False)
    await sync_catalogue(app.state.access_catalogue)
    await _execute(tenant_db.db.superuser_url, GRANT_SQL)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await dispose_engine()


async def test_granted_principal_gets_the_fixture_findings_with_file_and_line(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/terms/coverage", headers=headers(ALICE_ID))
    assert response.status_code == 200
    body = response.json()
    assert body["commit"] == COMMIT
    assert body["available"] is True
    assert [(f["file"], f["line"], f["term"], f["suggestedKey"]) for f in body["findings"]] == [
        (f"{FIXTURE_DIR}/schemas.py", 7, "Variation", "record.type.variation"),
        (f"{FIXTURE_DIR}/templates/email/ncr_raised.j2", 3, "NCR", "record.type.ncr"),
    ]


async def test_without_the_grant_it_is_403(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/terms/coverage", headers=headers(CAROL_ID))
    assert response.status_code == 403


async def test_a_build_without_a_findings_file_reports_unavailable(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TERMS_LINT_FINDINGS", str(tmp_path / "missing.json"))
    response = await client.get("/api/v1/terms/coverage", headers=headers(ALICE_ID))
    assert response.status_code == 200
    assert response.json() == {"commit": COMMIT, "available": False, "findings": []}
