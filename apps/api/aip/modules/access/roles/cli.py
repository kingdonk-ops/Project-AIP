"""``aip-access seed-roles --tenant <id> [--tenant <id> ...]``: backfill system roles (ACCESS-02).

Connects as ``aip_app`` through ``DATABASE_URL`` (RLS applies), syncs the permission catalogue
from the module manifests, then runs ``seed_default_roles`` for each tenant in its own transaction.
Idempotent. Tenants are named explicitly: under FORCE RLS no application role can list every
tenant, and new tenants are seeded by provisioning (TENANCY-05). Customised roles are reported,
not changed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from aip.modules.access.roles.seed import seed_default_roles
from aip.modules.access.service import sync_catalogue
from aip.platform.access import build_catalogue, load_manifests
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

__all__ = ["main"]

_MODULES_DIR = Path(__file__).resolve().parents[2]


async def _seed(tenants: Sequence[UUID]) -> int:
    try:
        if not await sync_catalogue(build_catalogue(load_manifests(_MODULES_DIR))):
            print("DATABASE_URL is not set", file=sys.stderr)
            return 2
        for tenant in tenants:
            ctx = RequestContext(tenant_id=tenant, request_id=new_request_id())
            with use_context(ctx):
                async with with_tenant(ctx) as conn:
                    report = await seed_default_roles(conn)
            print(
                f"{tenant}: created {len(report.created)}, updated {len(report.updated)}"
                + "".join(
                    f"; {role} customised, not given {codes}"
                    for role, codes in report.pending.items()
                )
            )
    finally:
        await dispose_engine()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aip-access")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed-roles", help="create or sync the 11 system roles")
    seed.add_argument("--tenant", type=UUID, action="append", required=True, help="tenant id")
    args = parser.parse_args(argv)
    return asyncio.run(_seed(args.tenant))


if __name__ == "__main__":
    raise SystemExit(main())
