"""Published interface of the approvals module (APPROVALS-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the workflow rows join their transaction and RLS applies.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.engine.evaluator import available_transitions
from aip.modules.approvals.errors import NoActiveDefinitionError
from aip.modules.approvals.schemas import (
    StateSpec,
    TransitionSpec,
    WorkflowDefinition,
    WorkflowDefinitionSpec,
    WorkflowInstance,
)
from aip.modules.approvals.service import DefinitionsService, InstancesService

__all__ = [
    "ApprovalsApi",
    "NoActiveDefinitionError",
    "StateSpec",
    "TransitionSpec",
    "WorkflowDefinition",
    "WorkflowDefinitionSpec",
    "WorkflowInstance",
    "available_transitions",
]

_definitions = DefinitionsService()
_instances = InstancesService(_definitions)


class ApprovalsApi:
    """The operations the approvals module offers to other modules."""

    async def start_instance(
        self, conn: AsyncConnection, record_type: str, record_id: UUID, project_id: UUID | None
    ) -> WorkflowInstance:
        """The record's workflow instance, started on the active definition if it has none."""
        return await _instances.start_instance(conn, record_type, record_id, project_id)

    async def get_active_definition(
        self, conn: AsyncConnection, record_type: str, project_id: UUID | None = None
    ) -> WorkflowDefinition:
        """The project's active definition for ``record_type``, else the tenant-wide one."""
        return await _definitions.get_active_definition(conn, record_type, project_id)
