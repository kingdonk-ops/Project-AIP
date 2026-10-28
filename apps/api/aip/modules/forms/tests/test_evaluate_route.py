"""FORMS-02 integration: the evaluate route against real Postgres (testcontainers).

A kaefer-demo admin publishes the coating ITR, then evaluates answers against its revision; the
server returns the shared ``AnswerEvaluation`` in camelCase. The route also works on a draft (so a
template can be tested before publishing), needs ``form.view``, and hides another tenant's revision
as a 404. Permissions come from the test grant provider (``conftest``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from tests.fixtures.postgres import TenantDb

from .conftest import ALICE, BOB, CAROL, CAROL_ID, su_fetch

TEMPLATES = "/api/v1/forms/templates"
REVISIONS = "/api/v1/forms/revisions"
COATING = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "coating-itr-min.json").read_text("utf-8")
)


async def _upload(client: httpx.AsyncClient) -> dict[str, Any]:
    body = {"code": "coating-itr", "name": "Coating ITR", "kind": "inspection", "schema": COATING}
    response = await client.post(TEMPLATES, json=body, headers=ALICE)
    assert response.status_code == 201, response.text
    return response.json()


async def _publish(client: httpx.AsyncClient, revision_id: str) -> None:
    published = await client.post(f"{REVISIONS}/{revision_id}/publish", headers=ALICE)
    assert published.status_code == 200, published.text


FAILING = {"answers": {"dft_avg": {"value": 0.18, "unit": "mm"}}, "mode": "submit"}


async def test_evaluate_a_published_revision(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    await _publish(client, rev1)

    row = await su_fetch(
        db, "SELECT evaluator_version FROM form_revisions WHERE id = $1::uuid", rev1
    )
    assert row[0][0] == "1"

    response = await client.post(f"{REVISIONS}/{rev1}/evaluate", json=FAILING, headers=ALICE)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["failed"] == ["dft_avg"]
    assert result["complete"] is False
    assert any(
        e["fieldKey"] == "blast_standard" and e["code"] == "REQUIRED" for e in result["errors"]
    )


async def test_evaluate_works_on_a_draft(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]  # still a draft: never published

    response = await client.post(f"{REVISIONS}/{rev1}/evaluate", json=FAILING, headers=ALICE)
    assert response.status_code == 200, response.text
    assert response.json()["failed"] == ["dft_avg"]


async def test_another_tenant_gets_404(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    await _publish(client, rev1)

    denied = await client.post(f"{REVISIONS}/{rev1}/evaluate", json=FAILING, headers=BOB)
    assert denied.status_code == 404


async def test_a_viewer_without_form_view_is_forbidden(
    client: httpx.AsyncClient, db: TenantDb, grants: Any
) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    await _publish(client, rev1)

    grants.by_user[CAROL_ID] = set()  # drop form.view
    forbidden = await client.post(f"{REVISIONS}/{rev1}/evaluate", json=FAILING, headers=CAROL)
    assert forbidden.status_code == 403


async def test_an_extra_body_key_is_422(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = await _upload(client)
    rev1 = created["revision"]["id"]
    await _publish(client, rev1)

    bad = await client.post(
        f"{REVISIONS}/{rev1}/evaluate",
        json={"answers": {}, "mode": "submit", "complete": True},
        headers=ALICE,
    )
    assert bad.status_code == 422
