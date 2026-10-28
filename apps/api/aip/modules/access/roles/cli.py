"""``aip-access``: role maintenance commands.

``seed-roles --tenant <id> [--tenant <id> ...]``: backfill system roles (ACCESS-02).

Connects as ``aip_app`` through ``DATABASE_URL`` (RLS applies), syncs the permission catalogue
from the module manifests, then runs ``seed_default_roles`` for each tenant in its own transaction.
Idempotent. Tenants are named explicitly: under FORCE RLS no application role can list every
tenant, and new tenants are seeded by provisioning (TENANCY-05). Customised roles are reported,
not changed.

``bootstrap-admin --admin <tenant-id>,<email>,<idp-alias> [...]`` (TESTING-09; runs only when
``AIP_ENV`` is development, demo or test): make each email its tenant's ``tenant_admin`` before
their first SSO sign-in, so the fixture tenants have someone who can create projects and assign
roles. ``--viewer <tenant-id>,<email>,<idp-alias>`` (TESTING-12) also gives each email the read-only
``VIEWER_ROLE`` (no ``project.create``), for the e2e lane's server-403 journey.
Idempotent; run after ``seed-roles``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from aip.modules.access.roles.seed import seed_default_roles
from aip.modules.access.roles.service import (
    VIEWER_ROLE,
    bootstrap_tenant_admin,
    bootstrap_tenant_viewer,
)
from aip.modules.access.service import sync_catalogue
from aip.platform.access import build_catalogue, load_manifests
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

__all__ = ["BOOTSTRAP_ENVS", "main"]

# Allowlist, not a production denylist: an unset or misspelled AIP_ENV must not grant admin.
BOOTSTRAP_ENVS = frozenset({"development", "demo", "test"})

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


def _admin(value: str) -> tuple[UUID, str, str]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3 or "@" not in parts[1] or not parts[2]:
        raise argparse.ArgumentTypeError("expected <tenant-id>,<email>,<idp-alias>")
    try:
        return UUID(parts[0]), parts[1], parts[2]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a tenant id: {parts[0]}") from exc


async def _bootstrap(
    admins: Sequence[tuple[UUID, str, str]], viewers: Sequence[tuple[UUID, str, str]] = ()
) -> int:
    jobs = [(a, bootstrap_tenant_admin, "tenant_admin") for a in admins] + [
        (v, bootstrap_tenant_viewer, VIEWER_ROLE) for v in viewers
    ]
    try:
        for (tenant, email, alias), bootstrap, role in jobs:
            ctx = RequestContext(tenant_id=tenant, request_id=new_request_id())
            with use_context(ctx):
                async with with_tenant(ctx) as conn:
                    assigned = await bootstrap(conn, tenant_id=tenant, email=email, idp_alias=alias)
            print(f"{tenant}: {email} {role} {'assigned' if assigned else 'already held'}")
    finally:
        await dispose_engine()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aip-access")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed-roles", help="create or sync the 11 system roles")
    seed.add_argument("--tenant", type=UUID, action="append", required=True, help="tenant id")
    boot = commands.add_parser("bootstrap-admin", help="dev/demo: seed each tenant's first admin")
    boot.add_argument(
        "--admin", type=_admin, action="append", required=True, help="<tenant-id>,<email>,<idp>"
    )
    boot.add_argument(
        "--viewer",
        type=_admin,
        action="append",
        default=[],
        help=f"<tenant-id>,<email>,<idp>: also seed a read-only {VIEWER_ROLE}",
    )
    args = parser.parse_args(argv)
    if args.command == "bootstrap-admin":
        env = os.environ.get("AIP_ENV", "").strip().lower()
        if env not in BOOTSTRAP_ENVS:
            print(
                f"bootstrap-admin runs only when AIP_ENV is one of {sorted(BOOTSTRAP_ENVS)}",
                file=sys.stderr,
            )
            return 1
        return asyncio.run(_bootstrap(args.admin, args.viewer))
    return asyncio.run(_seed(args.tenant))


if __name__ == "__main__":
    raise SystemExit(main())
