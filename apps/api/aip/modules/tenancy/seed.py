"""Fixture tenants for dev, CI and staging (TENANCY-01 step 2). Synthetic; nothing is read from AIP.

    uv run python -m aip.modules.tenancy.seed

Upserts ``kaefer-demo`` and ``tenant-b`` as the table owner through ``DATABASE_MIGRATOR_URL``
(``aip_app`` may only read ``tenants``). FORCE RLS binds the owner too, so each row is written
with ``app.tenant_id`` set to that row's id, transaction-local. Idempotent: a re-run restores the
fixture values (name, slug, region, ``active``, not deleted). Refuses to run, before connecting,
unless ``AIP_ENV`` is ``development``, ``test`` or ``demo``. Run it before ``python -m aip.modules.identity.seeds``: the login
directory references these tenants.

ENT-01: each fixture tenant also gets a sandbox subscription (``kaefer-demo`` on ``professional``,
``tenant-b`` on ``core``), upserted the same way; a re-run restores it and bumps the entitlement
version so caches drop the old values.

TENANCY-03: each fixture tenant also gets its ``owner`` organisation, named after the tenant;
a re-run leaves an existing live one (same name, ignoring case) as it is.

The ids are the shared fixture ids (AGENTS.md, ``apps/api/tests/conftest.py``, the identity seeds).
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

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
    plan_code: str
    status: str = "active"
    deployment_shape: str = "pooled"


FIXTURE_TENANTS: tuple[FixtureTenant, ...] = (
    FixtureTenant(KAEFER_DEMO_ID, "kaefer-demo", "Kaefer Demo", "ap-southeast-2", "professional"),
    FixtureTenant(TENANT_B_ID, "tenant-b", "Tenant B", "ap-southeast-2", "core"),
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

# Synthetic sandbox terms for the fixtures (no contract reference: sandbox needs none, ADR 0017).
FIXTURE_STARTS_ON = date(2026, 7, 1)
FIXTURE_RENEWAL_DATE = date(2027, 6, 30)

_UPSERT_SUBSCRIPTION = text(
    """
    INSERT INTO tenant_subscription
        (id, tenant_id, plan_code, plan_version, term, starts_on, renewal_date, status)
    VALUES (:id, :tenant_id, :plan_code, 1, 'sandbox', :starts_on, :renewal_date, 'active')
    ON CONFLICT (tenant_id) DO UPDATE
      SET plan_code = EXCLUDED.plan_code,
          plan_version = EXCLUDED.plan_version,
          term = EXCLUDED.term,
          starts_on = EXCLUDED.starts_on,
          ends_on = NULL,
          renewal_date = EXCLUDED.renewal_date,
          seat_limits = '{}'::jsonb,
          storage_gb = NULL,
          add_ons = '{}'::text[],
          contract_ref = NULL,
          status = EXCLUDED.status,
          entitlement_version = tenant_subscription.entitlement_version + 1,
          deleted_at = NULL,
          updated_at = now()
    """
)

_INSERT_OWNER_ORGANISATION = text(
    """
    INSERT INTO organisations (id, tenant_id, name, org_type, status)
    VALUES (:id, :tenant_id, :name, 'owner', 'active')
    ON CONFLICT (tenant_id, lower(name)) WHERE deleted_at IS NULL DO NOTHING
    """
)


class SeedRefusedError(RuntimeError):
    pass


# An allowlist (review 11 L4): an unset, misspelt or new AIP_ENV refuses, like production.
SEED_ENVS = frozenset({"development", "test", "demo"})


def _refuse_in_production(env: str | None) -> None:
    current = env if env is not None else os.environ.get("AIP_ENV", "")
    if current not in SEED_ENVS:
        raise SeedRefusedError(
            f"seeds run only when AIP_ENV is development, test or demo (got {current!r})"
        )


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
                await conn.execute(
                    _UPSERT_SUBSCRIPTION,
                    {
                        "id": uuid4(),
                        "tenant_id": tenant.id,
                        "plan_code": tenant.plan_code,
                        "starts_on": FIXTURE_STARTS_ON,
                        "renewal_date": FIXTURE_RENEWAL_DATE,
                    },
                )
                await conn.execute(
                    _INSERT_OWNER_ORGANISATION,
                    {"id": uuid4(), "tenant_id": tenant.id, "name": tenant.name},
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
