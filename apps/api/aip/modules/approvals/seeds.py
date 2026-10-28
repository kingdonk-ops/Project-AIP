"""Dev and demo seed: the inspection lifecycle preset and the ``demo`` workflow in ``kaefer-demo``.

    python -m aip.modules.approvals.seeds

Connects as ``aip_app`` through ``DATABASE_URL`` (RLS applies) and installs ``inspection_standard``
tenant-wide in the ``kaefer-demo`` fixture tenant through ``install_preset``, so a re-run is a no-op
and a changed preset file is published as the next version. ``tenant-b`` gets nothing, so the
cross-tenant journeys see no definition there.

TESTING-13 (ADR 0035 §9): it also publishes the ``demo`` workflow (``aip.modules.approvals.demo``)
tenant-wide in ``kaefer-demo``, the same way, for the transition journeys on the compose stack
(the API serves ``demo`` records only with ``AIP_APPROVALS_DEMO_RECORDS=1``).

Refuses to run, before connecting, unless ``AIP_ENV`` is ``development``, ``test`` or ``demo``.
Run it after the tenancy seed.
"""

from __future__ import annotations

import asyncio
import os
import sys
from uuid import UUID

from aip.modules.approvals.demo import DEMO_DEFINITION_KEY, DEMO_RECORD_TYPE, demo_spec
from aip.modules.approvals.schemas import WorkflowDefinition
from aip.modules.approvals.service import DefinitionsService
from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

__all__ = ["SEED_DEMO_TENANTS", "SEED_ENVS", "SEED_PRESETS", "SeedRefusedError", "main", "seed"]

# An allowlist (review 11 L4): an unset, misspelt or new AIP_ENV refuses, like production.
SEED_ENVS = frozenset({"development", "test", "demo"})
KAEFER_DEMO_ID = UUID("00000000-0000-4000-8000-00000000000a")
SEED_PRESETS: tuple[tuple[UUID, str], ...] = ((KAEFER_DEMO_ID, "inspection_standard"),)
SEED_DEMO_TENANTS: tuple[UUID, ...] = (KAEFER_DEMO_ID,)


class SeedRefusedError(RuntimeError):
    pass


async def seed(*, env: str | None = None) -> list[WorkflowDefinition]:
    """Install each seed preset in its tenant; returns the active definitions."""
    current = env if env is not None else os.environ.get("AIP_ENV", "")
    if current not in SEED_ENVS:
        raise SeedRefusedError(
            f"seeds run only when AIP_ENV is development, test or demo (got {current!r})"
        )
    definitions = DefinitionsService()
    installed: list[WorkflowDefinition] = []
    for tenant_id, preset_key in SEED_PRESETS:
        ctx = RequestContext(tenant_id=tenant_id, request_id=new_request_id())
        with use_context(ctx):
            async with with_tenant(ctx) as conn:
                installed.append(await definitions.install_preset(conn, preset_key))
    for tenant_id in SEED_DEMO_TENANTS:
        ctx = RequestContext(tenant_id=tenant_id, request_id=new_request_id())
        with use_context(ctx):
            async with with_tenant(ctx) as conn:
                installed.append(
                    await definitions.install_spec(
                        conn, DEMO_DEFINITION_KEY, DEMO_RECORD_TYPE, demo_spec()
                    )
                )
    return installed


async def _run() -> list[WorkflowDefinition]:
    try:
        return await seed()
    finally:
        await dispose_engine()


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        installed = asyncio.run(_run())
    except SeedRefusedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for definition in installed:
        print(f"approvals seeds: {definition.key} v{definition.version} ({definition.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
