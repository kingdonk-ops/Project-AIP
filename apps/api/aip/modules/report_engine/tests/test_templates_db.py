"""REPORTS-01 integration tests: the loader, the API and ``report_templates`` on real Postgres.

The app and the loader connect as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB
principal header; permissions from the ``grants`` fixture. The fixture tenants are kaefer-demo (A)
and tenant-b (B); A never sees B's rows. ``project-summary/internal/v1`` is the example package.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.report_engine.api import ReportTemplatesApi, render_html
from aip.modules.report_engine.loader import run
from aip.modules.report_engine.routes import PREVIEW_CSP
from aip.modules.report_engine.template_package import load_package
from aip.platform.db.migrator import repo_root

from .conftest import ALICE, BOB, CAROL, DAVE, su_fetch

TEMPLATES = "/api/v1/reports/templates"
ROOT = repo_root() / "config" / "report-templates"
EXAMPLE = ROOT / "project-summary" / "internal" / "v1"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TENANTS = (TENANT_A_ID, TENANT_B_ID)
api = ReportTemplatesApi()


async def _load(root: Path = ROOT) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    status = await run(root, TENANTS, out=out, err=err)
    return status, out.getvalue(), err.getvalue()


def _upload(**definition: Any) -> dict[str, Any]:
    package = load_package(EXAMPLE)
    return {
        "definition": {**json.loads(json.dumps(package.definition)), **definition},
        "body": package.body,
        "css": package.css,
        "sampleData": dict(package.sample_data),
        "assets": {n: base64.b64encode(a.data).decode() for n, a in package.assets.items()},
    }


async def _template_id(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    response = await client.get(TEMPLATES, headers=headers)
    assert response.status_code == 200, response.text
    (item,) = response.json()["items"]
    return item["id"]


async def test_the_loader_installs_once_per_tenant(app: FastAPI, db: TenantDb) -> None:
    status, out, err = await _load()
    assert (status, err) == (0, "")
    assert out.splitlines() == [f"{t}: installed 1, unchanged 0" for t in TENANTS]

    rows = await su_fetch(
        db, "SELECT tenant_id, status, source, version FROM report_templates ORDER BY tenant_id"
    )
    assert rows == [(t, "published", "config", 1) for t in TENANTS]
    events = await su_fetch(
        db,
        "SELECT tenant_id, payload FROM domain_events"
        " WHERE event_name = 'report.template_published' ORDER BY tenant_id",
    )
    assert [e[0] for e in events] == list(TENANTS)
    payload = events[0][1] if isinstance(events[0][1], dict) else json.loads(events[0][1])
    assert {k: payload[k] for k in ("key", "variant", "version", "recordType")} == {
        "key": "project-summary",
        "variant": "internal",
        "version": 1,
        "recordType": "project",
    }

    status, out, _ = await _load()
    assert status == 0
    assert out.splitlines() == [f"{t}: installed 0, unchanged 1" for t in TENANTS]
    assert await su_fetch(db, "SELECT count(*) FROM report_templates") == [(2,)]
    assert await su_fetch(
        db, "SELECT count(*) FROM domain_events WHERE event_name = 'report.template_published'"
    ) == [(2,)]


async def test_a_changed_version_stops_the_loader(
    app: FastAPI, db: TenantDb, tmp_path: Path
) -> None:
    await _load()
    before = await su_fetch(db, "SELECT id, content_sha256, updated_at FROM report_templates")

    root = tmp_path / "report-templates"
    copy = root / "project-summary" / "internal" / "v1"
    shutil.copytree(EXAMPLE, copy)
    (copy / "style.css").write_text(
        (copy / "style.css").read_text("utf-8") + "\n.extra { color: #000000; }\n", "utf-8"
    )
    status, _, err = await _load(root)
    assert status == 1
    assert "TEMPLATE_VERSION_CHANGED key=project-summary variant=internal version=1" in err
    assert await su_fetch(db, "SELECT id, content_sha256, updated_at FROM report_templates") == (
        before
    )


async def test_upload_publish_and_version_conflicts(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    created = await client.post(TEMPLATES, json=_upload(version=2), headers=ALICE)
    assert created.status_code == 201, created.text
    draft = created.json()
    assert (draft["status"], draft["version"], draft["source"]) == ("draft", 2, "upload")
    assert draft["assets"] == [
        {
            "name": "logo.png",
            "contentType": "image/png",
            "sizeBytes": (EXAMPLE / "assets" / "logo.png").stat().st_size,
            "sha256": load_package(EXAMPLE).assets["logo.png"].sha256,
        }
    ]

    published = await client.post(f"{TEMPLATES}/{draft['id']}/publish", headers=ALICE)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published" and published.json()["publishedAt"]

    again = await client.post(TEMPLATES, json=_upload(version=2), headers=ALICE)
    assert again.status_code == 409 and again.json()["code"] == "TEMPLATE_VERSION_CONFLICT"
    skipped = await client.post(TEMPLATES, json=_upload(version=4), headers=ALICE)
    assert skipped.status_code == 409 and skipped.json()["expectedVersion"] == 3

    twice = await client.post(f"{TEMPLATES}/{draft['id']}/publish", headers=ALICE)
    assert twice.status_code == 409 and twice.json()["code"] == "TEMPLATE_NOT_DRAFT"
    deleted = await client.delete(f"{TEMPLATES}/{draft['id']}", headers=ALICE)
    assert deleted.status_code == 409 and deleted.json()["code"] == "TEMPLATE_NOT_DRAFT"

    async with db.with_tenant(TENANT_A_ID) as conn:
        latest = await api.get_published(conn, "project-summary", "internal")
        assert latest is not None and latest.version == 2
        document = render_html(
            latest,
            latest.sample_data,
            labels={k: k for k in latest.definition["termKeys"]},
            locale="en-AU",
            time_zone="Australia/Perth",
            unit_system="metric",
        )
        assert "L592" in document.html and document.assets["logo.png"].startswith(b"\x89PNG")


async def test_a_draft_can_be_deleted_and_its_version_is_not_reused(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    draft = (await client.post(TEMPLATES, json=_upload(version=2), headers=ALICE)).json()
    assert (await client.delete(f"{TEMPLATES}/{draft['id']}", headers=ALICE)).status_code == 204
    gone = await client.get(f"{TEMPLATES}/{draft['id']}", headers=ALICE)
    assert gone.status_code == 404 and gone.json()["code"] == "TEMPLATE_NOT_FOUND"
    reused = await client.post(TEMPLATES, json=_upload(version=2), headers=ALICE)
    assert reused.status_code == 409 and reused.json()["expectedVersion"] == 3


async def test_retire_keeps_the_row(app: FastAPI, client: httpx.AsyncClient, db: TenantDb) -> None:
    await _load()
    template_id = await _template_id(client, ALICE)
    retired = await client.post(f"{TEMPLATES}/{template_id}/retire", headers=ALICE)
    assert retired.status_code == 200 and retired.json()["status"] == "retired"
    again = await client.post(f"{TEMPLATES}/{template_id}/retire", headers=ALICE)
    assert again.status_code == 409 and again.json()["code"] == "TEMPLATE_NOT_PUBLISHED"
    async with db.with_tenant(TENANT_A_ID) as conn:
        assert await api.get_published(conn, "project-summary", "internal") is None
        kept = await api.get(conn, UUID(template_id))
        assert kept is not None and kept.status == "retired"


async def test_a_bad_package_is_422_and_writes_nothing(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    bad = FIXTURES / "script-tag"
    raw = {
        "definition": json.loads((bad / "template.json").read_text("utf-8")),
        "body": (bad / "body.html.j2").read_text("utf-8"),
        "css": (bad / "style.css").read_text("utf-8"),
        "sampleData": json.loads((bad / "sample-data.json").read_text("utf-8")),
        "assets": {},
    }
    response = await client.post(TEMPLATES, json=raw, headers=ALICE)
    assert response.status_code == 422, response.text
    body = response.json()
    assert (body["code"], body["path"]) == ("HTML_POLICY", "body") and body["detail"]
    assert await su_fetch(db, "SELECT count(*) FROM report_templates") == [(0,)]

    unknown = {**_upload(), "script": "x"}
    assert (await client.post(TEMPLATES, json=unknown, headers=ALICE)).status_code == 422


async def test_a_published_row_is_frozen_in_the_database(app: FastAPI, db: TenantDb) -> None:
    await _load()
    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="report template is published") as raised:
            await conn.execute(text("UPDATE report_templates SET body = '<p>x</p>'"))
        assert getattr(raised.value.orig, "sqlstate", None) == "23514"
    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="report template is published"):
            await conn.execute(text("UPDATE report_templates SET deleted_at = now()"))
    async with db.with_tenant(TENANT_A_ID) as conn:
        result = await conn.execute(text("UPDATE report_templates SET status = 'retired'"))
        assert result.rowcount == 1
    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="report template is published"):
            await conn.execute(text("UPDATE report_templates SET status = 'published'"))
    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("DELETE FROM report_templates"))


async def test_rls_fails_closed_and_isolates_tenants(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    async with db.no_tenant() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM report_templates"))).scalar_one()
        assert count == 0

    kaefer_id = await _template_id(client, ALICE)
    bob_id = await _template_id(client, BOB)
    assert kaefer_id != bob_id
    response = await client.get(f"{TEMPLATES}/{kaefer_id}", headers=BOB)
    assert response.status_code == 404 and response.json()["code"] == "TEMPLATE_NOT_FOUND"
    for path in ("publish", "retire", "preview"):
        crossed = await client.post(f"{TEMPLATES}/{kaefer_id}/{path}", headers=BOB)
        assert crossed.status_code == 404, path


async def test_permissions_deny_by_default(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    assert (await client.get(TEMPLATES, headers=DAVE)).status_code == 403
    assert (await client.get(TEMPLATES, headers=CAROL)).status_code == 200
    denied = await client.post(TEMPLATES, json=_upload(version=2), headers=CAROL)
    assert denied.status_code == 403
    template_id = await _template_id(client, CAROL)
    assert (
        await client.post(f"{TEMPLATES}/{template_id}/retire", headers=CAROL)
    ).status_code == 403
    assert (
        await client.post(f"{TEMPLATES}/{template_id}/preview", headers=CAROL)
    ).status_code == 200


async def test_list_filters_and_pages(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    for version in (2, 3):
        created = await client.post(TEMPLATES, json=_upload(version=version), headers=ALICE)
        assert created.status_code == 201, created.text
    first = (await client.get(TEMPLATES, params={"limit": 2}, headers=ALICE)).json()
    assert [i["version"] for i in first["items"]] == [1, 2] and first["nextCursor"]
    assert "body" not in first["items"][0] and "assets" not in first["items"][0]
    rest = (
        await client.get(
            TEMPLATES, params={"limit": 2, "cursor": first["nextCursor"]}, headers=ALICE
        )
    ).json()
    assert [i["version"] for i in rest["items"]] == [3] and rest["nextCursor"] is None
    drafts = (await client.get(TEMPLATES, params={"status": "draft"}, headers=ALICE)).json()
    assert [i["version"] for i in drafts["items"]] == [2, 3]
    none = (await client.get(TEMPLATES, params={"recordType": "inspection"}, headers=ALICE)).json()
    assert none["items"] == []
    bad = await client.get(TEMPLATES, params={"cursor": "not-a-cursor"}, headers=ALICE)
    assert bad.status_code == 422 and bad.json()["code"] == "INVALID_CURSOR"


async def test_preview_renders_the_sample_inline(
    app: FastAPI, client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _load()
    template_id = await _template_id(client, ALICE)
    response = await client.post(f"{TEMPLATES}/{template_id}/preview", headers=ALICE)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == PREVIEW_CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "L592" in response.text
    assert "data:image/png;base64," in response.text
    # No URL anywhere (the wrapper's own ``http-equiv`` meta is the only "http" in the page).
    assert "http:" not in response.text and "https:" not in response.text
    assert "//" not in response.text.replace("<!doctype html>", "")
    assert "AWST" in response.text
