"""APPROVALS-02 Part B: server-side JSONLogic guards over host-module facts, on Postgres."""

from __future__ import annotations

import re
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection
from tests.conftest import ALICE_ID, TENANT_A_ID
from tests.fixtures.postgres import TenantDb

from aip.modules.approvals.api import (
    register_guard_context_provider,
    unregister_guard_context_provider,
)
from aip.modules.approvals.service import DefinitionsService
from aip.modules.approvals.tests.conftest import (
    act,
    ctx,
    history,
    publish,
    signed,
    start,
    su_fetch,
)
from aip.modules.approvals.tests.fixtures import demo_spec
from aip.platform.context import use_context

HEX64 = re.compile(r"^[0-9a-f]{64}$")
PHOTOS_CLEAN = {"==": [{"var": "record.allPhotosClean"}, True]}


class Facts:
    """The test provider's answer for ``demo`` records; tests flip it."""

    def __init__(self) -> None:
        self.all_photos_clean: bool = False
        self.fail: bool = False
        self.calls: list[UUID] = []

    async def __call__(self, conn: AsyncConnection, record_id: UUID) -> dict[str, Any]:
        self.calls.append(record_id)
        if self.fail:
            raise RuntimeError("db down")
        return {"allPhotosClean": self.all_photos_clean}


@pytest.fixture
def facts() -> Iterator[Facts]:
    provider = Facts()
    register_guard_context_provider("demo", provider)
    try:
        yield provider
    finally:
        unregister_guard_context_provider("demo")


def guarded_spec() -> dict[str, Any]:
    spec = demo_spec()
    for t in spec["transitions"]:
        if t["action"] == "approve":
            t["guard"] = PHOTOS_CLEAN
            t["guardMessageKey"] = "approvals.guard.photos_not_clean"
    return spec


@pytest.fixture
async def guarded(db: TenantDb) -> UUID:
    return await publish(db, guarded_spec())


async def decision_count(db: TenantDb, instance_id: str) -> int:
    rows = await su_fetch(
        db,
        "SELECT count(*) FROM workflow_decision_history WHERE instance_id = $1",
        UUID(instance_id),
    )
    return int(rows[0][0])


async def submitted(client: httpx.AsyncClient) -> dict[str, Any]:
    instance = await start(client)
    assert (await act(client, instance["id"], "submit")).status_code == 200
    return instance


def alice_signed() -> dict[str, str]:
    """Alice with a fresh aal2 sign-in (``approve`` is critical), built per call so it is fresh."""
    return signed(TENANT_A_ID, ALICE_ID)


@pytest.mark.usefixtures("guarded")
async def test_a_false_guard_refuses_and_a_true_one_is_recorded(
    client: httpx.AsyncClient, db: TenantDb, facts: Facts
) -> None:
    instance = await submitted(client)
    refused = await act(client, instance["id"], "approve", headers=alice_signed())
    assert refused.status_code == 422
    assert refused.json() == {
        "code": "GUARD_FAILED",
        "messageKey": "approvals.guard.photos_not_clean",
    }
    assert await decision_count(db, instance["id"]) == 1

    facts.all_photos_clean = True
    response = await act(client, instance["id"], "approve", headers=alice_signed())
    assert response.status_code == 200, response.text
    found = await history(client, instance["id"])
    assert found["chainValid"] is True
    guard_result = found["entries"][-1]["guardResult"]
    assert guard_result["passed"] is True
    assert guard_result["guard"] == PHOTOS_CLEAN
    assert HEX64.match(guard_result["factsHash"])
    assert found["entries"][0]["guardResult"] is None  # submit has no guard
    assert facts.calls and all(c == UUID(instance["recordId"]) for c in facts.calls)


@pytest.mark.usefixtures("guarded")
async def test_a_provider_error_fails_closed(
    client: httpx.AsyncClient, db: TenantDb, facts: Facts
) -> None:
    instance = await submitted(client)
    facts.fail = True
    response = await act(client, instance["id"], "approve", headers=alice_signed())
    assert response.status_code == 422
    assert response.json()["code"] == "GUARD_ERROR"
    current = await client.get(
        f"/api/v1/approvals/instances/{instance['id']}", headers=alice_signed()
    )
    assert current.json()["currentState"] == "submitted"
    assert await decision_count(db, instance["id"]) == 1


@pytest.mark.usefixtures("guarded")
async def test_no_provider_means_empty_record_facts(client: httpx.AsyncClient) -> None:
    instance = await submitted(client)
    response = await act(client, instance["id"], "approve", headers=alice_signed())
    assert response.status_code == 422
    assert response.json()["code"] == "GUARD_FAILED"


@pytest.mark.usefixtures("guarded")
async def test_available_transitions_show_the_guard_reason(
    client: httpx.AsyncClient, facts: Facts
) -> None:
    instance = await submitted(client)
    path = f"/api/v1/approvals/instances/{instance['id']}"
    by_action = {
        t["action"]: t
        for t in (await client.get(path, headers=alice_signed())).json()["availableTransitions"]
    }
    assert by_action["approve"]["allowed"] is False
    assert by_action["approve"]["reasonKey"] == "approvals.guard.photos_not_clean"
    assert by_action["reject"]["allowed"] is True

    facts.all_photos_clean = True
    by_action = {
        t["action"]: t
        for t in (await client.get(path, headers=alice_signed())).json()["availableTransitions"]
    }
    assert by_action["approve"] == {**by_action["approve"], "allowed": True, "reasonKey": None}


@pytest.mark.usefixtures("demo_records")
async def test_numeric_facts_compare_as_numbers_and_odd_facts_fail_closed(
    client: httpx.AsyncClient, db: TenantDb
) -> None:
    spec = demo_spec()
    for t in spec["transitions"]:
        if t["action"] == "reject":
            t["guard"] = {"<=": [{"var": "record.claimed"}, {"var": "record.limit"}]}
    await publish(db, spec)
    answer: dict[str, Any] = {"claimed": Decimal("1000"), "limit": Decimal("900.5")}

    async def provider(conn: AsyncConnection, record_id: UUID) -> dict[str, Any]:
        return answer

    register_guard_context_provider("demo", provider)
    try:
        instance = await submitted(client)
        refused = await act(client, instance["id"], "reject")
        assert refused.json()["code"] == "GUARD_FAILED"  # 1000 <= 900.5 is false as numbers
        answer = {"claimed": object(), "limit": 1}
        odd = await act(client, instance["id"], "reject")
        assert odd.status_code == 422
        assert odd.json()["code"] == "GUARD_ERROR"
        answer = {"claimed": Decimal("10"), "limit": 900}
        assert (await act(client, instance["id"], "reject")).status_code == 200
    finally:
        unregister_guard_context_provider("demo")


async def test_a_definition_with_a_disallowed_guard_is_refused(db: TenantDb) -> None:
    spec = demo_spec()
    spec["transitions"][1]["guard"] = {"reduce": [[1, 2], {"+": [1, 1]}, 0]}
    with use_context(ctx()):
        async with db.with_tenant(TENANT_A_ID) as conn:
            with pytest.raises(ValidationError) as caught:
                await DefinitionsService().create_draft(conn, "guarded", "demo", spec)
    [issue] = caught.value.errors()
    assert issue["loc"] == ("transitions", 1, "guard")
    assert "operator not allowed: reduce" in issue["msg"]
