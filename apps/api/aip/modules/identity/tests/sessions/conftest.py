"""Fixtures for the IDENTITY-03 integration tests: a migrated database with both fixture tenants
and three users, the real app wired with sessions (no header stub), and helpers to issue sessions.

Seeding runs as the superuser; assertions go through ``aip_app`` (RLS on) or the API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from tests.conftest import ALICE_ID, BOB_ID, TENANT_A_ID, TENANT_B_ID
from tests.fixtures.postgres import (  # noqa: F401 - re-exported pytest fixtures
    TenantDb,
    _execute,  # pyright: ignore[reportPrivateUsage]
    _fetch,  # pyright: ignore[reportPrivateUsage]
    bootstrapped_db,  # pyright: ignore[reportUnusedImport]
    empty_db,  # pyright: ignore[reportUnusedImport]
    migrated_db,  # pyright: ignore[reportUnusedImport]
    pg_superuser_url,  # pyright: ignore[reportUnusedImport]
    tenant_db,  # pyright: ignore[reportUnusedImport]
)

from aip.main import create_app
from aip.modules.identity.sessions import IssuedSession, issue_session
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

from ..test_rate_limit_redis import redis_url  # noqa: F401 - re-exported fixture

ORIGIN = "https://app.example.test"
CAROL_ID = UUID("00000000-0000-4000-8000-00000000ca01")  # a second kaefer-demo user

SEED_SQL = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active');"
    "INSERT INTO app_user (id, tenant_id, user_class, email, display_name, status) VALUES "
    f"('{ALICE_ID}', '{TENANT_A_ID}', 'staff', 'alice@kaefer.test', 'Alice', 'active'), "
    f"('{CAROL_ID}', '{TENANT_A_ID}', 'staff', 'carol@kaefer.test', 'Carol', 'active'), "
    f"('{BOB_ID}', '{TENANT_B_ID}', 'staff', 'bob@acme.test', 'Bob', 'active')"
)


async def su_execute(db: TenantDb, sql: str) -> None:
    await _execute(db.db.superuser_url, sql)


async def su_fetch(db: TenantDb, sql: str, *args: object) -> list[tuple[Any, ...]]:
    return await _fetch(db.db.superuser_url, sql, *args)


async def new_session(
    tenant: UUID,
    user: UUID,
    *,
    kc_sid: str | None = None,
    aal: int = 1,
    presented_sid: str | None = None,
) -> IssuedSession:
    async with with_tenant(tenant) as conn:
        return await issue_session(
            conn,
            user_id=user,
            user_class="staff",
            aal=aal,
            amr=["pwd"],
            authenticated_at=datetime.now(UTC),
            kc_sid=kc_sid,
            ip="203.0.113.7",
            user_agent="pytest",
            presented_sid=presented_sid,
        )


def cookies(issued: IssuedSession) -> dict[str, str]:
    return {"cookie": f"__Host-aip_sid={issued.sid}; __Host-aip_csrf={issued.csrf}"}


def unsafe(issued: IssuedSession) -> dict[str, str]:
    """Headers for a cookie-authenticated POST/DELETE that passes CSRF."""
    return {**cookies(issued), "origin": ORIGIN, "x-csrf-token": issued.csrf}


@pytest.fixture
def use_redis() -> bool:
    return False


@pytest.fixture
def redis(request: pytest.FixtureRequest, use_redis: bool) -> Iterator[str | None]:
    yield request.getfixturevalue("redis_url") if use_redis else None


@pytest.fixture
async def app(
    tenant_db: TenantDb,  # noqa: F811 - the re-exported fixture
    redis: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[FastAPI]:
    await su_execute(tenant_db, SEED_SQL)
    monkeypatch.setenv("AIP_ENV", "test")
    monkeypatch.delenv("AUTH_TEST_STUB", raising=False)
    monkeypatch.setenv("APP_ORIGIN", ORIGIN)
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    if redis is None:
        monkeypatch.delenv("REDIS_URL", raising=False)
    else:
        monkeypatch.setenv("REDIS_URL", redis)
    await dispose_engine()
    application = create_app(env="test", tracing=False)
    yield application
    await dispose_engine()


@pytest.fixture
def db(app: FastAPI, tenant_db: TenantDb) -> TenantDb:  # noqa: F811
    return tenant_db


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, client=("203.0.113.7", 1234))
    async with httpx.AsyncClient(transport=transport, base_url=ORIGIN) as c:
        yield c
