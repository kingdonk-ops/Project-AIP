"""Published interface of the inspections module (INSPECTIONS-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the inspection, its workflow instance and its ``inspection.created`` event
join their transaction and RLS applies.

``create_inspection`` is the cross-module contract plus ``source_ref_id``, which a scope task
(SCOPEWORK-03) or a re-inspection needs. It checks ``inspection.create`` on the project, the asset,
the project and the template's current published revision exactly as ``POST /inspections`` does.

``get_current_responses`` (INSPECTIONS-02) is the current answer per field and their evaluation,
the same shape as ``GET /inspections/{id}/responses``, for report_engine and issues.

INSPECTIONS-03: ``get_itp_step`` and ``is_step_released`` let scope_work ask about a step without
reading inspections tables (``is_step_released`` is true only for a released or waived step with
no NCR hold, false for an unknown one). Issues puts an NCR hold on a step with ``place_hold`` and
lifts it with ``clear_hold``; it has authorised its NCR, so neither checks a permission. They raise
``StepAlreadyReleasedError``, ``StepAlreadyHeldError`` and ``HoldMismatchError`` (409 over HTTP).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.api import Actor
from aip.modules.inspections import itp
from aip.modules.inspections import repository as repo
from aip.modules.inspections.itp import (
    HoldMismatchError,
    StepAlreadyHeldError,
    StepAlreadyReleasedError,
)
from aip.modules.inspections.responses import current_responses
from aip.modules.inspections.schemas import CurrentResponses, InspectionOut, ItpStepOut
from aip.modules.inspections.service import InspectionService, NewInspection, current_state
from aip.platform.access import PolicyService

__all__ = [
    "CurrentResponses",
    "HoldMismatchError",
    "InspectionOut",
    "InspectionsApi",
    "ItpStepOut",
    "StepAlreadyHeldError",
    "StepAlreadyReleasedError",
]


class InspectionsApi:
    """The operations the inspections module offers to other modules."""

    async def create_inspection(
        self,
        conn: AsyncConnection,
        policy: PolicyService,
        actor: Actor,
        *,
        asset_id: UUID,
        project_id: UUID | None,
        template_id: UUID,
        kind: str,
        source: str,
        source_ref_id: UUID | None = None,
    ) -> InspectionOut:
        """Create a ``draft`` inspection pinned to the template's current published revision."""
        row, _ = await InspectionService(policy).create(
            conn,
            actor,
            NewInspection(
                asset_id=asset_id,
                template_id=template_id,
                kind=kind,
                project_id=project_id,
                source=source,
                source_ref_id=source_ref_id,
            ),
        )
        return InspectionOut.model_validate(row)

    async def get_inspection(
        self, conn: AsyncConnection, inspection_id: UUID
    ) -> InspectionOut | None:
        """The live inspection visible on ``conn``, or ``None``. No permission check."""
        row = await repo.get_inspection(conn, inspection_id)
        return None if row is None else InspectionOut.model_validate(row)

    async def get_state(self, conn: AsyncConnection, inspection_id: UUID) -> str | None:
        """The inspection's workflow ``current_state`` (the truth), or ``None`` when not visible."""
        row = await repo.get_inspection(conn, inspection_id)
        return None if row is None else await current_state(conn, row)

    async def get_current_responses(
        self, conn: AsyncConnection, inspection_id: UUID
    ) -> CurrentResponses | None:
        """The current answers of the inspection visible on ``conn`` and their evaluation, or
        ``None``. No permission check."""
        row = await repo.get_inspection(conn, inspection_id)
        return None if row is None else await current_responses(conn, row)

    async def get_itp_step(self, conn: AsyncConnection, step_id: UUID) -> ItpStepOut | None:
        """The live ITP step visible on ``conn``, or ``None``. No permission check."""
        row = await repo.get_step(conn, step_id)
        return None if row is None else ItpStepOut.of(row)

    async def is_step_released(self, conn: AsyncConnection, step_id: UUID) -> bool:
        """True only for a released or waived step with no NCR hold; false for an unknown one."""
        return await itp.is_step_released(conn, step_id)

    async def place_hold(
        self, conn: AsyncConnection, step_id: UUID, *, issue_id: UUID
    ) -> ItpStepOut:
        """Put issue ``issue_id``'s NCR hold on the step (emits ``itp_step.hold_changed``)."""
        return await itp.place_hold(conn, step_id, issue_id=issue_id)

    async def clear_hold(
        self, conn: AsyncConnection, step_id: UUID, *, issue_id: UUID
    ) -> ItpStepOut:
        """Lift issue ``issue_id``'s hold from the step (emits ``itp_step.hold_changed``)."""
        return await itp.clear_hold(conn, step_id, issue_id=issue_id)
