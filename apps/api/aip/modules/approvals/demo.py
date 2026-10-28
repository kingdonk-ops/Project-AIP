"""The dev/test-only ``demo`` workflow host (TESTING-13 Part B, was APPROVALS-07; ADR 0035 §9).

APPROVALS-02 proved its transition journeys in-process only: no record type existed whose
definition, permissions and fixture users a whole deployment could seed. This file is that record
type, for the compose stack (CI lane ``e2e-skeleton``) and local development. It is never a
product feature:

- ``python -m aip.modules.approvals.demo seed`` publishes the ``demo`` workflow for record type
  ``approvals_demo`` in ``kaefer-demo`` (idempotent, as ``aip_app`` with RLS). It refuses to run
  unless ``AIP_ENV`` is ``development``, ``test`` or ``demo`` (an allowlist: an unset or misspelt
  value refuses, like production).
- Its transitions use real catalogue permissions: ``submit``/``resubmit`` need ``approvals.start``,
  ``approve``/``reject`` need ``approvals.design``. The ``kaefer-demo`` submitter fixture user
  (``alice@kaefer.test``) holds both through ``tenant_admin`` (``admin-bootstrap``), whose
  ``approvals`` level is ``admin`` (ADR 0027). The test-only ``approvals.demo.*`` codes stay out
  of the catalogue (ADR 0035 §9).
- ``approve`` is critical and guarded by ``record.allPhotosClean``. Its sign-off policy
  ``approvals.demo_approve`` is seeded by ``aip.modules.identity.seeds`` with min aal 1 and a
  10-minute window, because the mock IdP has no second factor: a fresh sign-in passes, a stale one
  is asked to step up or countersign like any other critical action.
- The record resolver and the guard facts provider answer only in those environments; anywhere
  else the resolver sees no record (404) and the provider gives no facts (the guard fails closed).
- The fixture switch ``PUT /api/v1/approvals/demo-records/{id}/facts`` (``approvals.design``,
  hidden from the OpenAPI document, 404 outside those environments) sets ``allPhotosClean`` for a
  record of the caller's tenant. The facts live in this process's memory: the compose API is one
  process, and losing them on a restart only makes the guard fail closed again.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import os
import sys
from collections.abc import Sequence
from typing import Annotated, Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.guards.context_providers import (
    RecordRef,
    provider_for,
    register_guard_context_provider,
    register_record_resolver,
    resolver_for,
)
from aip.modules.approvals.schemas import WorkflowDefinition
from aip.modules.approvals.service import DefinitionsService
from aip.platform.access import AccessPrincipal, current_principal, requires
from aip.platform.context import RequestContext, get_context, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import with_tenant

__all__ = [
    "DEFINITION_KEY",
    "DEMO_ENVS",
    "RECORD_TYPE",
    "SIGNOFF_ACTION",
    "DemoRefusedError",
    "demo_enabled",
    "demo_facts",
    "demo_spec",
    "install",
    "main",
    "router",
    "seed",
]

RECORD_TYPE: Final = "approvals_demo"
DEFINITION_KEY: Final = "demo"
SIGNOFF_ACTION: Final = "approvals.demo_approve"
TENANT_A_ID: Final = UUID("00000000-0000-4000-8000-00000000000a")  # kaefer-demo
# An allowlist (review 11 L4): an unset, misspelt or new AIP_ENV refuses, like production.
DEMO_ENVS: Final = frozenset({"development", "test", "demo"})


class DemoRefusedError(RuntimeError):
    """The demo host was asked to run outside a development, test or demo environment."""


def demo_enabled(env: str | None = None) -> bool:
    current = env if env is not None else os.environ.get("AIP_ENV", "")
    return current.strip().lower() in DEMO_ENVS


def _transition(action: str, src: str, dst: str, permission: str, **extra: Any) -> dict[str, Any]:
    return {
        "action": action,
        "from": src,
        "to": dst,
        "requiredPermission": permission,
        "guard": None,
        "sideEffects": [],
        "critical": False,
        "labelKey": f"approvals.demo.action.{action}",
        **extra,
    }


_SPEC: Final[dict[str, Any]] = {
    "states": [
        {"code": "draft", "labelKey": "approvals.demo.state.draft"},
        {"code": "submitted", "labelKey": "approvals.demo.state.submitted"},
        {"code": "approved", "labelKey": "approvals.demo.state.approved", "terminal": True},
        {"code": "rejected", "labelKey": "approvals.demo.state.rejected"},
    ],
    "initial": "draft",
    "transitions": [
        _transition("submit", "draft", "submitted", "approvals.start"),
        _transition(
            "approve",
            "submitted",
            "approved",
            "approvals.design",
            critical=True,
            signoffAction=SIGNOFF_ACTION,
            guard={"==": [{"var": "record.allPhotosClean"}, True]},
            guardMessageKey="approvals.guard.photos_not_clean",
        ),
        _transition("reject", "submitted", "rejected", "approvals.design"),
        _transition("resubmit", "rejected", "submitted", "approvals.start"),
    ],
}


def demo_spec() -> dict[str, Any]:
    """``draft -> submitted -> approved | rejected``; ``approve`` is critical and guarded."""
    return copy.deepcopy(_SPEC)


# --- the host module: record resolver, guard facts and the fixture switch -----------------------

_facts: dict[tuple[UUID, UUID], bool] = {}


async def resolve_record(conn: AsyncConnection, record_id: UUID) -> RecordRef | None:
    """Every demo record exists tenant-wide, but only where the demo host is enabled."""
    del conn, record_id
    return RecordRef(project_id=None) if demo_enabled() else None


async def demo_facts(conn: AsyncConnection, record_id: UUID) -> dict[str, Any]:
    """``{"allPhotosClean": ...}`` for the record in the bound tenant (``{}`` when disabled)."""
    del conn
    if not demo_enabled():
        return {}
    return {"allPhotosClean": _facts.get((get_context().tenant_id, record_id), False)}


def install() -> None:
    """Register the resolver and facts provider for ``approvals_demo`` (once per process)."""
    if resolver_for(RECORD_TYPE) is None:
        register_record_resolver(RECORD_TYPE, resolve_record)
    if provider_for(RECORD_TYPE) is None:
        register_guard_context_provider(RECORD_TYPE, demo_facts)


class DemoFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    all_photos_clean: bool = Field(alias="allPhotosClean")


router = APIRouter(prefix="/approvals/demo-records", tags=["approvals"])


async def _demo_only() -> None:
    """404 for everyone, before any permission check, outside development, test and demo."""
    if not demo_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@router.put(
    "/{record_id}/facts",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
    dependencies=[Depends(_demo_only), Depends(requires("approvals.design"))],
)
async def set_demo_facts(
    record_id: UUID,
    body: DemoFacts,
    principal: Annotated[AccessPrincipal, Depends(current_principal)],
) -> Response:
    """The e2e fixture switch for ``allPhotosClean`` (development, test and demo only)."""
    _facts[(principal.tenant_id, record_id)] = body.all_photos_clean
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- the seed ------------------------------------------------------------------------------------


async def seed(*, env: str | None = None, tenant_id: UUID = TENANT_A_ID) -> WorkflowDefinition:
    """Publish the ``demo`` workflow in ``tenant_id`` (idempotent); refused outside dev/test."""
    if not demo_enabled(env):
        raise DemoRefusedError(
            "the approvals demo seed runs only when AIP_ENV is development, test or demo"
            f" (got {(env if env is not None else os.environ.get('AIP_ENV', ''))!r})"
        )
    ctx = RequestContext(tenant_id=tenant_id, request_id=new_request_id())
    with use_context(ctx):
        async with with_tenant(ctx) as conn:
            return await DefinitionsService().install_spec(
                conn, DEFINITION_KEY, RECORD_TYPE, demo_spec()
            )


async def _seed_and_dispose() -> WorkflowDefinition:
    try:
        return await seed()
    finally:
        await dispose_engine()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aip.modules.approvals.demo")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="publish the demo workflow in kaefer-demo (dev/test/demo)")
    parser.parse_args(argv)
    if not demo_enabled():
        print(
            f"the approvals demo seed runs only when AIP_ENV is one of {sorted(DEMO_ENVS)}",
            file=sys.stderr,
        )
        return 1
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    definition = asyncio.run(_seed_and_dispose())
    print(f"approvals demo: {definition.key} v{definition.version} active for {RECORD_TYPE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
