"""Unit tests for the fixture-tenant seed (TENANCY-01 step 2). No database."""

from __future__ import annotations

from typing import Any

import pytest
from tests.conftest import TENANT_A_ID, TENANT_B_ID

from aip.modules.tenancy import seed


def _no_connect(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("the seed connected to a database")


def test_main_refuses_production_without_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "production")
    monkeypatch.setenv("DATABASE_MIGRATOR_URL", "postgresql://aip_owner:x@db.invalid:5432/aip")
    monkeypatch.setattr(seed, "create_migrator_engine", _no_connect)
    assert seed.main() != 0


async def test_seed_refuses_production_without_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "create_migrator_engine", _no_connect)
    with pytest.raises(seed.SeedRefusedError):
        await seed.seed("postgresql://aip_owner:x@db.invalid:5432/aip", env="production")


def test_main_without_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_ENV", "development")
    monkeypatch.delenv("DATABASE_MIGRATOR_URL", raising=False)
    monkeypatch.setattr(seed, "create_migrator_engine", _no_connect)
    assert seed.main() != 0


def test_fixture_tenants_are_the_shared_fixtures() -> None:
    assert seed.KAEFER_DEMO_ID == TENANT_A_ID
    assert seed.TENANT_B_ID == TENANT_B_ID
    by_slug = {t.slug: t for t in seed.FIXTURE_TENANTS}
    assert set(by_slug) == {"kaefer-demo", "tenant-b"}
    assert by_slug["kaefer-demo"].id == TENANT_A_ID
    assert by_slug["kaefer-demo"].name == "Kaefer Demo"
    assert by_slug["tenant-b"].name == "Tenant B"
    for tenant in seed.FIXTURE_TENANTS:
        assert (tenant.region_code, tenant.status) == ("ap-southeast-2", "active")
