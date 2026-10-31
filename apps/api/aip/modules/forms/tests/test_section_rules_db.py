"""FORMS-10 integration tests: the supervisor-review setting and a version 2 publish, on Postgres.

``hasSupervisorReview`` defaults to true, can be set on create and changed with PATCH, and is
exposed to other modules through ``FormsApi.get_template``. Another tenant's template is a 404.
A version 2 revision with section rules publishes, stays frozen with its rules, and the evaluate
route returns the per-section result.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from tests.conftest import TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.forms.api import FormsApi

from .conftest import ALICE, BOB, CAROL, su_fetch

TEMPLATES = "/api/v1/forms/templates"
REVISIONS = "/api/v1/forms/revisions"
api = FormsApi()

DFT_OK = {
    "and": [
        {">=": [{"var": "answers.dft_1"}, 250]},
        {">=": [{"var": "answers.dft_2"}, 250]},
    ]
}
SCHEMA_V2: dict[str, Any] = {
    "schemaVersion": 2,
    "sections": [
        {
            "key": "coating",
            "label": "Coating",
            "fields": [
                {"key": "dft_1", "type": "decimal", "label": "DFT 1", "required": True},
                {"key": "dft_2", "type": "decimal", "label": "DFT 2", "required": True},
            ],
            "rules": [{"key": "dft_ok", "expr": DFT_OK, "label": "Every DFT must be >= 250"}],
        }
    ],
}


async def _create(client: httpx.AsyncClient, **extra: Any) -> dict[str, Any]:
    body = {"code": "dft-check", "name": "DFT check", "kind": "inspection", "schema": SCHEMA_V2}
    response = await client.post(TEMPLATES, json={**body, **extra}, headers=ALICE)
    assert response.status_code == 201, response.text
    return response.json()


async def test_supervisor_review_defaults_to_true(client: httpx.AsyncClient, db: TenantDb) -> None:
    created = await _create(client)
    assert created["template"]["hasSupervisorReview"] is True
    template_id = created["template"]["id"]

    detail = await client.get(f"{TEMPLATES}/{template_id}", headers=ALICE)
    assert detail.status_code == 200 and detail.json()["hasSupervisorReview"] is True
    page = await client.get(TEMPLATES, headers=ALICE)
    assert [item["hasSupervisorReview"] for item in page.json()["items"]] == [True]


async def test_supervisor_review_can_be_off_on_create_and_changed_later(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await _create(client, hasSupervisorReview=False)
    template_id = created["template"]["id"]
    detail = await client.get(f"{TEMPLATES}/{template_id}", headers=ALICE)
    assert detail.json()["hasSupervisorReview"] is False

    async with db.with_tenant(TENANT_A_ID) as conn:
        template = await api.get_template(conn, UUID(template_id))
    assert template is not None and template.has_supervisor_review is False

    version = detail.json()["syncVersion"]
    updated = await client.patch(
        f"{TEMPLATES}/{template_id}",
        json={"hasSupervisorReview": True, "expectedSyncVersion": version},
        headers=ALICE,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["hasSupervisorReview"] is True
    assert updated.json()["name"] == "DFT check"  # untouched
    assert updated.json()["syncVersion"] == version + 1

    stale = await client.patch(
        f"{TEMPLATES}/{template_id}",
        json={"hasSupervisorReview": False, "expectedSyncVersion": version},
        headers=ALICE,
    )
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"

    rows = await su_fetch(db, "SELECT has_supervisor_review FROM form_templates")
    assert rows == [(True,)]


async def test_update_needs_form_manage_and_another_tenant_gets_404(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await _create(client)
    template_id = created["template"]["id"]
    url = f"{TEMPLATES}/{template_id}"
    body = {"hasSupervisorReview": False}

    assert (await client.patch(url, json=body, headers=CAROL)).status_code == 403
    assert (await client.patch(url, json=body, headers=BOB)).status_code == 404
    assert (await client.get(url, headers=BOB)).status_code == 404
    unknown = await client.patch(
        f"{TEMPLATES}/{template_id}", json={"supervisorReview": False}, headers=ALICE
    )
    assert unknown.status_code == 422

    rows = await su_fetch(db, "SELECT has_supervisor_review FROM form_templates")
    assert rows == [(True,)]


async def test_a_version_2_revision_with_rules_publishes_and_evaluates_per_section(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    created = await _create(client)
    revision_id = created["revision"]["id"]
    published = await client.post(f"{REVISIONS}/{revision_id}/publish", headers=ALICE)
    assert published.status_code == 200, published.text
    assert (
        published.json()["revision"]["schema"]["sections"][0]["rules"]
        == SCHEMA_V2["sections"][0]["rules"]
    )

    async with db.with_tenant(TENANT_A_ID) as conn:
        frozen = await api.get_revision(conn, UUID(revision_id))
    assert frozen is not None and frozen.schema["sections"][0]["rules"][0]["key"] == "dft_ok"

    failing = await client.post(
        f"{REVISIONS}/{revision_id}/evaluate",
        json={"answers": {"dft_1": 200, "dft_2": 250}},
        headers=ALICE,
    )
    assert failing.status_code == 200, failing.text
    assert failing.json()["sections"]["coating"] == {
        "visible": True,
        "missingRequired": [],
        "invalid": [],
        "failed": [],
        "ruleFailures": ["dft_ok"],
        "complete": False,
    }
    assert failing.json()["complete"] is False

    passing = await client.post(
        f"{REVISIONS}/{revision_id}/evaluate",
        json={"answers": {"dft_1": 300, "dft_2": 300}},
        headers=ALICE,
    )
    assert passing.json()["sections"]["coating"]["complete"] is True
    assert passing.json()["complete"] is True


async def test_a_rule_reading_an_unknown_field_fails_upload_and_lint_reports_warnings(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    bad = {
        "schemaVersion": 2,
        "sections": [
            {
                "key": "s",
                "label": "S",
                "fields": [{"key": "a", "type": "decimal", "label": "A"}],
                "rules": [
                    {"key": "r", "expr": {">": [{"var": "answers.nozzle_size"}, 1]}, "label": "x"}
                ],
            }
        ],
    }
    refused = await client.post(
        TEMPLATES,
        json={"code": "bad-rule", "name": "Bad", "kind": "inspection", "schema": bad},
        headers=ALICE,
    )
    assert refused.status_code == 422
    assert [i["code"] for i in refused.json()["issues"]] == ["UNKNOWN_REFERENCE"]

    hideable = {
        "schemaVersion": 2,
        "sections": [
            {
                "key": "opt",
                "label": "Optional",
                "visibleIf": {"==": [{"var": "context.kind"}, "inspection"]},
                "fields": [{"key": "a", "type": "decimal", "label": "A"}],
            },
            {
                "key": "end",
                "label": "End",
                "fields": [{"key": "b", "type": "text", "label": "B"}],
                "rules": [{"key": "r", "expr": {">": [{"var": "answers.a"}, 1]}, "label": "x"}],
            },
        ],
    }
    linted = await client.post("/api/v1/forms/lint", json={"schema": hideable}, headers=ALICE)
    assert linted.status_code == 200
    assert [(i["code"], i["severity"]) for i in linted.json()["issues"]] == [
        ("RULE_READS_HIDDEN_FIELD", "warning")
    ]
    accepted = await client.post(
        TEMPLATES,
        json={"code": "warned", "name": "Warned", "kind": "inspection", "schema": hideable},
        headers=ALICE,
    )
    assert accepted.status_code == 201, accepted.text
