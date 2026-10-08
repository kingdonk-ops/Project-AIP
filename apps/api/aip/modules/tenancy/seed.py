"""Fixture tenants for dev, CI and staging (TENANCY-01 step 2). Synthetic; nothing is read from AIP.

    uv run python -m aip.modules.tenancy.seed

Upserts ``kaefer-demo`` and ``tenant-b`` as the table owner through ``DATABASE_MIGRATOR_URL``
(``aip_app`` may only read ``tenants``). FORCE RLS binds the owner too, so each row is written
with ``app.tenant_id`` set to that row's id, transaction-local. Idempotent: a re-run restores the
fixture values (name, slug, region, ``active``, not deleted). Refuses to run, before connecting,
when ``AIP_ENV=production``. Run it before ``python -m aip.modules.identity.seeds``: the login
directory references these tenants.

The ids are the shared fixture ids (AGENTS.md, ``apps/api/tests/conftest.py``, the identity seeds).
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from aip.platform.db.migrator.run import create_migrator_engine

KAEFER_DEMO_ID = UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B_ID = UUID("00000000-0000-4000-8000-00000000000b")


@dataclass(frozen=True)
class FixtureTenant:
    id: UUID
    slug: str
    name: str
    region_code: str
    status: str = "active"
    deployment_shape: str = "pooled"


FIXTURE_TENANTS: tuple[FixtureTenant, ...] = (
    FixtureTenant(KAEFER_DEMO_ID, "kaefer-demo", "Kaefer Demo", "ap-southeast-2"),
    FixtureTenant(TENANT_B_ID, "tenant-b", "Tenant B", "ap-southeast-2"),
)

_SET_TENANT = text("SELECT set_config('app.tenant_id', :tenant_id, true)")
_UPSERT = text(
    """
    INSERT INTO tenants (id, name, slug, deployment_shape, region_code, status)
    VALUES (:id, :name, :slug, :deployment_shape, :region_code, :status)
    ON CONFLICT (id) DO UPDATE
      SET name = EXCLUDED.name,
          slug = EXCLUDED.slug,
          deployment_shape = EXCLUDED.deployment_shape,
          region_code = EXCLUDED.region_code,
          status = EXCLUDED.status,
          deleted_at = NULL,
          updated_at = now()
    """
)


class SeedRefusedError(RuntimeError):
    pass


def _refuse_in_production(env: str | None) -> None:
    if (env if env is not None else os.environ.get("AIP_ENV", "")) == "production":
        raise SeedRefusedError("seeds refuse to run when AIP_ENV=production")


async def seed(url: str, *, env: str | None = None) -> int:
    """Upsert the fixture tenants; return how many. Raises ``SeedRefusedError`` in production."""
    _refuse_in_production(env)
    engine = create_migrator_engine(url)
    try:
        async with engine.begin() as conn:
            for tenant in FIXTURE_TENANTS:
                await conn.execute(_SET_TENANT, {"tenant_id": str(tenant.id)})
                await conn.execute(
                    _UPSERT,
                    {
                        "id": tenant.id,
                        "name": tenant.name,
                        "slug": tenant.slug,
                        "deployment_shape": tenant.deployment_shape,
                        "region_code": tenant.region_code,
                        "status": tenant.status,
                    },
                )
    finally:
        await engine.dispose()
    return len(FIXTURE_TENANTS)


def main() -> int:
    try:
        _refuse_in_production(None)
    except SeedRefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    url = os.environ.get("DATABASE_MIGRATOR_URL")
    if not url:
        print("DATABASE_MIGRATOR_URL is not set", file=sys.stderr)
        return 2
    try:
        count = asyncio.run(seed(url))
    except SeedRefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"tenancy seed: {count} fixture tenants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
