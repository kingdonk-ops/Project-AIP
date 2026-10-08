"""Shared API test fixtures.

Fixture tenants follow AGENTS.md: tenant A is ``kaefer-demo`` (alice@kaefer.test), tenant B is
``tenant-b`` (bob@acme.test). Their UUIDs are fixed here so every test agrees on them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

import pytest

from aip.platform.context import Principal
from tests.fixtures.postgres import (  # noqa: F401 - shared real-Postgres fixtures (TESTING-01)
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    migrations_copy,  # pyright: ignore[reportUnusedImport]
    owner_conn_for_seeding_only,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

TENANT_A_ID = UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B_ID = UUID("00000000-0000-4000-8000-00000000000b")
ALICE_ID = UUID("00000000-0000-4000-8000-0000000a11ce")
BOB_ID = UUID("00000000-0000-4000-8000-000000000b0b")
PROJECT_A1_ID = UUID("00000000-0000-4000-8000-0000000000a1")
PROJECT_B1_ID = UUID("00000000-0000-4000-8000-0000000000b1")


@dataclass(frozen=True)
class FixtureIds:
    tenant_a: UUID = TENANT_A_ID
    tenant_b: UUID = TENANT_B_ID
    alice: UUID = ALICE_ID
    bob: UUID = BOB_ID
    project_a1: UUID = PROJECT_A1_ID
    project_b1: UUID = PROJECT_B1_ID


class FixturePrincipalResolver:
    """Maps test bearer tokens to principals. Stands in for the identity session resolver."""

    def __init__(self, tokens: Mapping[str, Principal]) -> None:
        self._tokens = dict(tokens)

    async def resolve(self, headers: Mapping[str, str]) -> Principal | None:
        auth = headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer":
            return None
        return self._tokens.get(token.strip())


@dataclass
class FixtureMembershipResolver:
    """(tenant, actor) -> set of project ids the actor is a member of."""

    members: dict[tuple[UUID, UUID], set[UUID]] = field(
        default_factory=dict[tuple[UUID, UUID], set[UUID]]
    )

    async def is_member(self, *, tenant_id: UUID, actor_id: UUID | None, project_id: UUID) -> bool:
        if actor_id is None:
            return False
        return project_id in self.members.get((tenant_id, actor_id), set())


@pytest.fixture
def ids() -> FixtureIds:
    return FixtureIds()


@pytest.fixture
def principal_resolver() -> FixturePrincipalResolver:
    return FixturePrincipalResolver(
        {
            "token-alice": Principal(
                tenant_id=TENANT_A_ID, actor_id=ALICE_ID, asset_path_scope=("site_a.unit_1",)
            ),
            "token-bob": Principal(tenant_id=TENANT_B_ID, actor_id=BOB_ID, asset_path_scope=()),
        }
    )


@pytest.fixture
def membership_resolver() -> FixtureMembershipResolver:
    return FixtureMembershipResolver(
        {
            (TENANT_A_ID, ALICE_ID): {PROJECT_A1_ID},
            (TENANT_B_ID, BOB_ID): {PROJECT_B1_ID},
        }
    )
