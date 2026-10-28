"""The dev and demo ``demo`` record type for the workflow journeys on a deployed stack (TESTING-13).

ADR 0035 §9: APPROVALS-02's API journeys could not run against a whole deployment, because no
record type existed whose workflow, permissions and guard facts a stack could seed. This module is
that record type, for development, test and demo stacks only:

- ``DEMO_SPEC``, published as definition ``demo`` in ``kaefer-demo`` by ``aip.modules.approvals.seeds``:
  ``draft -> submitted -> approved | rejected`` (``resubmit`` from ``rejected``), using the real
  catalogue codes ``approvals.inspection.execute`` and ``approvals.inspection.approve``, which the
  fixture tenant admin holds. ``approve`` is guarded by ``record.allPhotosClean``. It is not
  ``critical``: the stack's fixture users sign in at aal 1 through the mock IdP, and the step-up
  journeys belong to IDENTITY-08.
- A ``demo`` record is a project of the tenant, so a journey creates one through the real projects
  API and nothing new is stored. The record resolver puts the instance on that project. The guard
  facts provider is the fixture switch: ``allPhotosClean`` is true once the project is ``active``
  (a journey flips it with ``PATCH /projects/{id}``).
- When no host module has registered one yet, the same project-backed resolver serves the
  ``inspection`` record type, so the APPROVALS-05 presets can be started before INSPECTIONS-01.

:func:`install_demo_records` registers them only when ``AIP_APPROVALS_DEMO_RECORDS=1`` and
``AIP_ENV`` is ``development``, ``test`` or ``demo``; it refuses production outright.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.guards.context_providers import (
    RecordRef,
    provider_for,
    register_guard_context_provider,
    register_record_resolver,
    resolver_for,
)
__all__ = [
    "DEMO_DEFINITION_KEY",
    "DEMO_ENVS",
    "DEMO_RECORDS_ENV",
    "DEMO_RECORD_TYPE",
    "DemoRecordsRefusedError",
    "demo_facts",
    "demo_spec",
    "install_demo_records",
    "resolve_project_record",
]

DEMO_RECORDS_ENV: Final = "AIP_APPROVALS_DEMO_RECORDS"
# An allowlist, as for the seeds (review 11 L4): an unset or misspelt AIP_ENV never registers.
DEMO_ENVS: Final = frozenset({"development", "test", "demo"})
DEMO_RECORD_TYPE: Final = "demo"
DEMO_DEFINITION_KEY: Final = "demo"
INSPECTION_RECORD_TYPE: Final = "inspection"

PHOTOS_CLEAN: Final[dict[str, Any]] = {"==": [{"var": "record.allPhotosClean"}, True]}

class DemoRecordsRefusedError(RuntimeError):
    pass


def _transition(action: str, src: str, dst: str, permission: str, **extra: Any) -> dict[str, Any]:
    return {
        "action": action,
        "from": src,
        "to": dst,
        "requiredPermission": permission,
        "labelKey": f"workflow.demo.action.{action}",
        **extra,
    }


def demo_spec() -> dict[str, Any]:
    """The ``demo`` workflow (a fresh copy each call)."""
    execute, approve = "approvals.inspection.execute", "approvals.inspection.approve"
    return {
        "states": [
            {"code": "draft", "labelKey": "workflow.demo.state.draft"},
            {"code": "submitted", "labelKey": "workflow.demo.state.submitted"},
            {"code": "approved", "labelKey": "workflow.demo.state.approved", "terminal": True},
            {"code": "rejected", "labelKey": "workflow.demo.state.rejected"},
        ],
        "initial": "draft",
        "transitions": [
            _transition("submit", "draft", "submitted", execute),
            _transition(
                "approve",
                "submitted",
                "approved",
                approve,
                guard=PHOTOS_CLEAN,
                guardMessageKey="workflow.demo.guard.photos_not_clean",
            ),
            _transition("reject", "submitted", "rejected", approve, requiresComment=True),
            _transition("resubmit", "rejected", "submitted", execute),
        ],
    }


async def _project(conn: AsyncConnection, project_id: UUID) -> Any:
    # Imported here: approvals depends on projects only when the demo records are switched on.
    from aip.modules.projects.api import ProjectsApi

    return await ProjectsApi().get_project(conn, project_id)


async def resolve_project_record(conn: AsyncConnection, record_id: UUID) -> RecordRef | None:
    """A project-backed record: the live project ``record_id`` of this tenant, else ``None``."""
    project = await _project(conn, record_id)
    return None if project is None else RecordRef(project_id=project.id)


async def demo_facts(conn: AsyncConnection, record_id: UUID) -> Mapping[str, Any]:
    """The fixture switch: the photos count as clean once the backing project is ``active``."""
    project = await _project(conn, record_id)
    return {"allPhotosClean": project is not None and project.status == "active"}


def install_demo_records(env: str | None = None) -> list[str]:
    """Register the project-backed record types when enabled; returns the types registered."""
    if os.environ.get(DEMO_RECORDS_ENV) != "1":
        return []
    current = env if env is not None else os.environ.get("AIP_ENV", "")
    if current not in DEMO_ENVS:
        raise DemoRecordsRefusedError(
            f"{DEMO_RECORDS_ENV}=1 is for development, test and demo stacks (AIP_ENV={current!r})"
        )
    installed: list[str] = []
    if resolver_for(DEMO_RECORD_TYPE) is None:
        register_record_resolver(DEMO_RECORD_TYPE, resolve_project_record)
        installed.append(DEMO_RECORD_TYPE)
    if provider_for(DEMO_RECORD_TYPE) is None:
        register_guard_context_provider(DEMO_RECORD_TYPE, demo_facts)
    # A real inspections module registers its own at import time, before create_app runs this.
    if resolver_for(INSPECTION_RECORD_TYPE) is None:
        register_record_resolver(INSPECTION_RECORD_TYPE, resolve_project_record)
        installed.append(INSPECTION_RECORD_TYPE)
    return installed
