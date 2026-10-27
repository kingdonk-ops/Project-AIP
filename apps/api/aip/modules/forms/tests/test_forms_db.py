"""FORMS-01 integration tests: the API and the two tables on real Postgres.

The app connects as ``aip_app`` (RLS on). Users come from the AUTH_TEST_STUB principal header;
permissions from the ``grants`` fixture. The two fixture tenants are kaefer-demo (A) and tenant-b
(B); A never sees B's rows. ``coating-itr-min`` is the golden template.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.forms.api import FormsApi

from .conftest import ALICE, BOB, CAROL, su_fetch

TEMPLATES = "/api/v1/forms/templates"
REVISIONS = "/api/v1/forms/revisions"
COATING = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "coating-itr-min.json").read_text("utf-8")
)
api = FormsApi()


async def _upload(
    client: httpx.AsyncClient, *, code: str = "coating-itr", headers: dict[str, str] = ALICE
) -> dict[str, Any]:
    body = {"code": code, "name": "Coating ITR", "kind": "inspection", "schema": COATING}
    response = await client.post(TEMPLATES, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


async def test_upload_creates_a_draft_revision_one(client: httpx.AsyncClient, db: TenantDb) -> None:
    result = await _upload(client)
    assert result["template"]["status"] == "draft"
    assert result["revision"]["revisionNo"] == 1 and result["revision"]["status"] == "draft"

    rows = await su_fetch(db, "SELECT status, revision_no FROM form_revisions")
    assert rows == [("draft", 1)]


async def test_duplicate_code_conflicts_and_a_broken_schema_writes_nothing(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    await _upload(client)
    again = await client.post(
        TEMPLATES,
        json={"code": "coating-itr", "name": "Dup", "kind": "inspection", "schema": COATING},
        headers=ALICE,
    )
    assert again.status_code == 409 and again.json()["code"] == "CODE_TAKEN"

    bad_schema = {
        "schemaVersion": 1,
        "sections": [
            {
                "key": "s",
                "label": "S",
                "fields": [
                    {
                        "key": "a",
                        "type": "boolean",
                        "label": "A",
                        "visibleIf": {"reduce": [[1], {"+": [1, 1]}, 0]},
                    }
                ],
            }
        ],
    }
    broken = await client.post(
        TEMPLATES,
        json={"code": "reduce-test", "name": "Bad", "kind": "inspection", "schema": bad_schema},
        headers=ALICE,
    )
    assert broken.status_code == 422
    body = broken.json()
    assert body["code"] == "TEMPLATE_INVALID" and body["issues"][0]["code"] == "EXPRESSION_INVALID"

    count = (await su_fetch(db, "SELECT count(*) FROM form_templates"))[0][0]
    assert count == 1  # only coating-itr; the broken upload wrote nothing


async def test_publish_freezes_the_revision_and_emits_one_event(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    template_id = created["template"]["id"]

    published = await client.post(f"{REVISIONS}/{rev1}/publish", headers=ALICE)
    assert published.status_code == 200, published.text
    result = published.json()
    assert result["revision"]["status"] == "published"
    assert _is_sha256(result["revision"]["schemaHash"])
    assert result["template"]["status"] == "active"
    assert result["template"]["currentRevisionNo"] == 1

    events = await su_fetch(
        db,
        "SELECT payload FROM domain_events WHERE event_name = 'form.revision_published'",
    )
    assert len(events) == 1
    payload = json.loads(events[0][0])  # asyncpg returns jsonb as text
    assert payload["revisionNo"] == 1
    assert payload["templateId"] == template_id


async def test_a_published_revision_cannot_be_changed_by_service_or_trigger(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    assert (await client.post(f"{REVISIONS}/{rev1}/publish", headers=ALICE)).status_code == 200

    frozen = await client.put(f"{REVISIONS}/{rev1}", json={"schema": COATING}, headers=ALICE)
    assert frozen.status_code == 409 and frozen.json()["code"] == "REVISION_FROZEN"

    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="form revision is frozen"):
            await conn.execute(
                text("UPDATE form_revisions SET schema = '{}' WHERE id = :id"), {"id": rev1}
            )
    async with db.with_tenant(TENANT_A_ID) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("DELETE FROM form_revisions WHERE id = :id"), {"id": rev1})


async def test_second_revision_supersedes_the_first_and_the_api_still_resolves_it(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    template_id = created["template"]["id"]
    assert (await client.post(f"{REVISIONS}/{rev1}/publish", headers=ALICE)).status_code == 200

    draft2 = await client.post(f"{TEMPLATES}/{template_id}/revisions", json={}, headers=ALICE)
    assert draft2.status_code == 201
    rev2 = draft2.json()
    assert rev2["revisionNo"] == 2 and rev2["schema"] == COATING

    dup = await client.post(f"{TEMPLATES}/{template_id}/revisions", json={}, headers=ALICE)
    assert dup.status_code == 409 and dup.json()["code"] == "DRAFT_EXISTS"

    published2 = await client.post(f"{REVISIONS}/{rev2['id']}/publish", headers=ALICE)
    assert published2.status_code == 200

    draft3 = await client.post(f"{TEMPLATES}/{template_id}/revisions", json={}, headers=ALICE)
    assert draft3.status_code == 201
    draft3_id = draft3.json()["id"]

    async with db.with_tenant(TENANT_A_ID) as conn:
        superseded = await api.get_revision(conn, UUID(rev1))
        assert superseded is not None and superseded.status == "superseded"
        current = await api.get_current_revision(conn, UUID(template_id))
        assert current is not None and current.revision_no == 2
        assert await api.get_revision(conn, UUID(draft3_id)) is None


async def test_two_concurrent_publishes_yield_one_success_and_one_conflict(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]

    first, second = await asyncio.gather(
        client.post(f"{REVISIONS}/{rev1}/publish", headers=ALICE),
        client.post(f"{REVISIONS}/{rev1}/publish", headers=ALICE),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]

    events = await su_fetch(
        db, "SELECT count(*) FROM domain_events WHERE event_name = 'form.revision_published'"
    )
    assert events[0][0] == 1


async def test_a_failed_emit_rolls_back_the_whole_publish(
    lenient_client: httpx.AsyncClient, db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await _upload(lenient_client)
    rev1 = created["revision"]["id"]
    template_id = created["template"]["id"]
    assert (
        await lenient_client.post(f"{REVISIONS}/{rev1}/publish", headers=ALICE)
    ).status_code == 200

    draft2 = await lenient_client.post(
        f"{TEMPLATES}/{template_id}/revisions", json={}, headers=ALICE
    )
    rev2 = draft2.json()["id"]

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr("aip.modules.forms.service.emit", boom)
    failed = await lenient_client.post(f"{REVISIONS}/{rev2}/publish", headers=ALICE)
    assert failed.status_code == 500

    rows = await su_fetch(db, "SELECT status FROM form_revisions WHERE id = $1::uuid", rev2)
    assert rows[0][0] == "draft"
    current = await su_fetch(
        db, "SELECT current_revision_id FROM form_templates WHERE id = $1::uuid", template_id
    )
    assert str(current[0][0]) == rev1  # the template still points at revision 1


async def test_another_tenant_sees_nothing(client: httpx.AsyncClient) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]

    assert (await client.get(f"{REVISIONS}/{rev1}", headers=BOB)).status_code == 404
    page = await client.get(TEMPLATES, headers=BOB)
    assert page.status_code == 200 and page.json()["items"] == []


async def test_a_viewer_cannot_upload_or_publish(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]

    denied_upload = await client.post(
        TEMPLATES,
        json={"code": "other", "name": "X", "kind": "inspection", "schema": COATING},
        headers=CAROL,
    )
    assert denied_upload.status_code == 403
    denied_publish = await client.post(f"{REVISIONS}/{rev1}/publish", headers=CAROL)
    assert denied_publish.status_code == 403

    count = (await su_fetch(db, "SELECT count(*) FROM form_templates"))[0][0]
    assert count == 1  # nothing the viewer did was written


async def test_an_unknown_body_field_is_rejected(client: httpx.AsyncClient) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    bad = await client.put(
        f"{REVISIONS}/{rev1}", json={"schema": COATING, "schemaHash": "x"}, headers=ALICE
    )
    assert bad.status_code == 422
