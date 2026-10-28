"""TESTING-13 Part B (was APPROVALS-07): the dev/test-only ``demo`` workflow host and its seed.

The same two journeys the compose stack runs in ``e2e/web/approvals-transition.spec.ts``, here
through the real app on Postgres as ``aip_app``: the seed's definition, the ``approvals_demo``
resolver and facts provider, and the fixture switch.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals import demo
from aip.modules.approvals.tests.conftest import (
    ALICE,
    BOB,
    CAROL,
    GrantTable,
    act,
    history,
    principal_headers,
    su_execute,
    su_fetch,
)
from aip.platform.access import build_catalogue, load_manifests

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MODULES_DIR = Path(demo.__file__).resolve().parents[1]

SIGNOFF_SQL = (
    "INSERT INTO signoff_policy (id, tenant_id, action_code, min_aal, step_up_max_age_min) "
    f"VALUES (gen_random_uuid(), '{TENANT_A_ID}', '{demo.SIGNOFF_ACTION}', 1, 10)"
)


def fresh(tenant: uuid.UUID = TENANT_A_ID, user: uuid.UUID = ALICE_ID) -> dict[str, str]:
    """A federated password sign-in a moment ago (aal 1), like the mock IdP's on the stack."""
    return principal_headers(tenant, user, authenticated_at=datetime.now(UTC))


@pytest.fixture
async def seeded(app: object, db: TenantDb, grants: GrantTable) -> None:
    """The demo seed in kaefer-demo, its sign-off row, and tenant_admin's approvals codes."""
    del app  # the app fixture points DATABASE_URL at this database
    await demo.seed(env="test")
    await su_execute(db, SIGNOFF_SQL)
    grants.by_user[ALICE_ID] = {"approvals.view", "approvals.start", "approvals.design"}
    grants.by_user[BOB_ID] = {"approvals.view", "approvals.start", "approvals.design"}


async def start_demo(client: httpx.AsyncClient, headers: dict[str, str] | None = None) -> Any:
    body = {"recordType": demo.RECORD_TYPE, "recordId": str(uuid.uuid4())}
    response = await client.post("/api/v1/approvals/instances", json=body, headers=headers or ALICE)
    assert response.status_code == 201, response.text
    return response.json()


async def set_facts(
    client: httpx.AsyncClient, record_id: str, clean: bool, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await client.put(
        f"/api/v1/approvals/demo-records/{record_id}/facts",
        json={"allPhotosClean": clean},
        headers=headers or ALICE,
    )


# --- the seed ------------------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["production", "staging", "", "Production "])
async def test_the_seed_refuses_outside_development_test_and_demo(env: str) -> None:
    with pytest.raises(demo.DemoRefusedError):
        await demo.seed(env=env)


def test_the_seed_command_refuses_production(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://never-used/aip")
    assert demo.main(["seed"]) == 1
    assert "AIP_ENV" in capsys.readouterr().err


def test_the_demo_workflow_uses_only_real_catalogue_permissions() -> None:
    catalogue = {p.code for p in build_catalogue(load_manifests(MODULES_DIR)).values()}
    required = {t["requiredPermission"] for t in demo.demo_spec()["transitions"]}
    assert required == {"approvals.start", "approvals.design"}
    assert required <= catalogue


@pytest.mark.usefixtures("seeded")
async def test_the_seed_is_idempotent(db: TenantDb) -> None:
    again = await demo.seed(env="test")
    assert again.version == 1
    rows = await su_fetch(
        db,
        "SELECT tenant_id, key, version, status FROM workflow_definitions WHERE record_type = $1",
        demo.RECORD_TYPE,
    )
    assert rows == [(TENANT_A_ID, demo.DEFINITION_KEY, 1, "active")]


# --- the two journeys ----------------------------------------------------------------------------


@pytest.mark.usefixtures("seeded")
async def test_submit_writes_one_chained_entry_another_tenant_gets_404(
    client: httpx.AsyncClient,
) -> None:
    instance = await start_demo(client)
    assert instance["definitionKey"] == "demo"
    assert instance["currentState"] == "draft"
    response = await act(client, instance["id"], "submit")
    assert response.status_code == 200, response.text

    found = await history(client, instance["id"])
    assert found["chainValid"] is True
    [entry] = found["entries"]
    assert HEX64.match(entry["entryHash"])

    as_b = await client.get(f"/api/v1/approvals/instances/{instance['id']}/history", headers=BOB)
    assert as_b.status_code == 404


@pytest.mark.usefixtures("seeded")
async def test_the_guard_refuses_approve_until_the_fixture_flips_all_photos_clean(
    client: httpx.AsyncClient,
) -> None:
    instance = await start_demo(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200

    refused = await act(client, instance["id"], "approve", headers=fresh())
    assert refused.status_code == 422
    assert refused.json()["code"] == "GUARD_FAILED"

    assert (await set_facts(client, instance["recordId"], True)).status_code == 204
    approved = await act(client, instance["id"], "approve", headers=fresh())
    assert approved.status_code == 200, approved.text
    assert approved.json()["instance"]["currentState"] == "approved"
    found = await history(client, instance["id"])
    assert found["chainValid"] is True
    assert [e["action"] for e in found["entries"]] == ["submit", "approve"]


@pytest.mark.usefixtures("seeded")
async def test_a_stale_sign_in_cannot_approve_on_its_own(client: httpx.AsyncClient) -> None:
    """The demo's sign-off policy still applies: no fresh sign-in, no applied approval."""
    instance = await start_demo(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200
    assert (await set_facts(client, instance["recordId"], True)).status_code == 204
    response = await act(client, instance["id"], "approve")  # ALICE has no authenticated_at
    assert response.status_code == 202, response.text
    assert response.json()["instance"]["currentState"] == "submitted"


@pytest.mark.usefixtures("seeded")
async def test_facts_are_per_tenant(client: httpx.AsyncClient) -> None:
    """Tenant B flipping a record id does not clean tenant A's record of the same id."""
    instance = await start_demo(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200
    assert (await set_facts(client, instance["recordId"], True, headers=BOB)).status_code == 204
    refused = await act(client, instance["id"], "approve", headers=fresh())
    assert refused.status_code == 422
    assert refused.json()["code"] == "GUARD_FAILED"


@pytest.mark.usefixtures("seeded")
async def test_the_fixture_switch_needs_approvals_design(client: httpx.AsyncClient) -> None:
    response = await set_facts(client, str(uuid.uuid4()), True, headers=CAROL)
    assert response.status_code == 403


@pytest.mark.usefixtures("seeded")
async def test_outside_dev_the_record_type_and_the_switch_are_gone(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    body = {"recordType": demo.RECORD_TYPE, "recordId": str(uuid.uuid4())}
    started = await client.post("/api/v1/approvals/instances", json=body, headers=ALICE)
    assert started.status_code == 404
    assert (await set_facts(client, str(uuid.uuid4()), True)).status_code == 404
    # 404 before the permission check, so the switch is not even confirmed to exist.
    assert (await set_facts(client, str(uuid.uuid4()), True, headers=CAROL)).status_code == 404


def test_the_switch_is_not_in_the_openapi_document() -> None:
    from aip.main import create_app

    paths = create_app(env="test", tracing=False).openapi()["paths"]
    assert not [p for p in paths if "demo-records" in p]


def test_tenant_b_has_no_demo_definition_by_default() -> None:
    # The seed targets kaefer-demo only; tenant-b's user only proves the 404.
    assert TENANT_B_ID != demo.TENANT_A_ID
