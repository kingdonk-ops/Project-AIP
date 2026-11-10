"""FORMS-11 integration tests: replacing a draft checks the template's ``syncVersion``.

The designer saves with ``expectedSyncVersion``. A save with the current version bumps it; a save
with an older one is 409 ``VERSION_CONFLICT`` and leaves the schema alone; a save without one is
not checked (the FORMS-04 JSON upload keeps working). Another tenant's draft is a 404.
"""

from __future__ import annotations

import copy
from typing import Any

import httpx
from tests.fixtures.postgres import TenantDb

from .conftest import ALICE, BOB

TEMPLATES = "/api/v1/forms/templates"
REVISIONS = "/api/v1/forms/revisions"

SCHEMA: dict[str, Any] = {
    "schemaVersion": 2,
    "sections": [
        {
            "key": "section_1",
            "label": "Section 1",
            "fields": [{"key": "field_1", "type": "text", "label": "Field 1"}],
        }
    ],
}


def _with_label(label: str) -> dict[str, Any]:
    schema = copy.deepcopy(SCHEMA)
    schema["sections"][0]["fields"][0]["label"] = label
    return schema


async def _draft(client: httpx.AsyncClient) -> tuple[str, str, int]:
    body = {"code": "dsg-1", "name": "Designer", "kind": "inspection", "schema": SCHEMA}
    response = await client.post(TEMPLATES, json=body, headers=ALICE)
    assert response.status_code == 201, response.text
    created = response.json()
    return (
        created["template"]["id"],
        created["revision"]["id"],
        created["template"]["syncVersion"],
    )


async def _sync_version(client: httpx.AsyncClient, template_id: str) -> int:
    detail = await client.get(f"{TEMPLATES}/{template_id}", headers=ALICE)
    assert detail.status_code == 200, detail.text
    return detail.json()["syncVersion"]


async def test_replace_with_the_current_version_bumps_it(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    template_id, revision_id, version = await _draft(client)
    response = await client.put(
        f"{REVISIONS}/{revision_id}",
        json={"schema": _with_label("First save"), "expectedSyncVersion": version},
        headers=ALICE,
    )
    assert response.status_code == 200, response.text
    assert response.json()["schema"]["sections"][0]["fields"][0]["label"] == "First save"
    assert await _sync_version(client, template_id) > version


async def test_replace_with_a_stale_version_conflicts_and_keeps_the_schema(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    template_id, revision_id, version = await _draft(client)
    first = await client.put(
        f"{REVISIONS}/{revision_id}",
        json={"schema": _with_label("First editor"), "expectedSyncVersion": version},
        headers=ALICE,
    )
    assert first.status_code == 200, first.text

    stale = await client.put(
        f"{REVISIONS}/{revision_id}",
        json={"schema": _with_label("Second editor"), "expectedSyncVersion": version},
        headers=ALICE,
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "VERSION_CONFLICT"

    current = await client.get(f"{REVISIONS}/{revision_id}", headers=ALICE)
    assert current.json()["schema"]["sections"][0]["fields"][0]["label"] == "First editor"
    assert await _sync_version(client, template_id) == version + 1


async def test_replace_without_a_version_is_not_checked(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    template_id, revision_id, version = await _draft(client)
    for label in ("Upload one", "Upload two"):
        response = await client.put(
            f"{REVISIONS}/{revision_id}", json={"schema": _with_label(label)}, headers=ALICE
        )
        assert response.status_code == 200, response.text
    assert await _sync_version(client, template_id) == version + 2

    # A publish with the version the uploads left still succeeds.
    latest = await _sync_version(client, template_id)
    published = await client.post(
        f"{REVISIONS}/{revision_id}/publish",
        json={"expectedSyncVersion": latest},
        headers=ALICE,
    )
    assert published.status_code == 200, published.text


async def test_another_tenant_cannot_replace_the_draft(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    _, revision_id, version = await _draft(client)
    response = await client.put(
        f"{REVISIONS}/{revision_id}",
        json={"schema": _with_label("Tenant B"), "expectedSyncVersion": version},
        headers=BOB,
    )
    assert response.status_code == 404, response.text

    current = await client.get(f"{REVISIONS}/{revision_id}", headers=ALICE)
    assert current.json()["schema"]["sections"][0]["fields"][0]["label"] == "Field 1"
