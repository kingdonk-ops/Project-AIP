"""OPS-11: the demo refuses to start when a tenant holds real customer data (ADR 0007)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from tests.conftest import TENANT_A_ID, TENANT_B_ID
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
from aip.modules.tenancy.api import RealDataInDemoError, assert_demo_has_no_real_customers
from aip.platform.db.engine import dispose_engine

SEED = (
    "INSERT INTO tenants (id, name, slug, region_code, status) VALUES "
    f"('{TENANT_A_ID}', 'Kaefer Demo', 'kaefer-demo', 'ap-southeast-2', 'active'), "
    f"('{TENANT_B_ID}', 'Tenant B', 'tenant-b', 'ap-southeast-2', 'active')"
)


@pytest.fixture
async def db(
    tenant_db: TenantDb,  # noqa: F811 - the re-exported fixture
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[TenantDb]:
    await _execute(tenant_db.db.superuser_url, SEED)
    monkeypatch.setenv("DATABASE_URL", tenant_db.db.app_url)
    await dispose_engine()
    yield tenant_db
    await dispose_engine()


async def test_synthetic_tenants_pass(db: TenantDb) -> None:
    await assert_demo_has_no_real_customers()


async def test_a_real_customer_tenant_stops_the_demo(
    db: TenantDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _execute(
        db.db.superuser_url,
        f"UPDATE tenants SET is_real_customer = true WHERE id = '{TENANT_B_ID}'",
    )
    with pytest.raises(RealDataInDemoError):
        await assert_demo_has_no_real_customers()

    monkeypatch.setenv("AIP_ENV", "demo")
    app = create_app(env="demo", tracing=False)
    with pytest.raises(RealDataInDemoError):
        async with app.router.lifespan_context(app):
            pass


async def test_without_a_database_the_demo_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RealDataInDemoError):
        await assert_demo_has_no_real_customers()
