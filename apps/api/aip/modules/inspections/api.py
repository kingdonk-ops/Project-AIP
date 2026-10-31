"""Published interface of the inspections module (INSPECTIONS-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the inspection, its workflow instance and its ``inspection.created`` event
join their transaction and RLS applies.

``create_inspection`` is the cross-module contract plus ``source_ref_id``, which a scope task
(SCOPEWORK-03) or a re-inspection needs. It checks ``inspection.create`` on the project, the asset,
the project and the template's current published revision exactly as ``POST /inspections`` does.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.api import Actor
from aip.modules.inspections import repository as repo
from aip.modules.inspections.schemas import InspectionOut
from aip.modules.inspections.service import InspectionService, NewInspection, current_state
from aip.platform.access import PolicyService

__all__ = ["InspectionOut", "InspectionsApi"]


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
