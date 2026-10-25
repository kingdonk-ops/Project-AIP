"""Published interface of the approvals module (APPROVALS-01, APPROVALS-02).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the workflow rows join their transaction and RLS applies.

APPROVALS-02: ``start_instance``, ``transition``, ``available_transitions`` and ``get_history``
take the policy service (``request.app.state.access_policy``) and an ``Actor`` (the caller's
``AccessPrincipal``, session facts and IP), so a host module's route gets the same permission,
guard and sign-off checks as ``/api/v1/approvals``. ``register_guard_context_provider`` lets a host
module supply the read-only ``record`` facts its record type's guards see, and
``register_record_resolver`` tells approvals which project a record belongs to (required before
``POST /approvals/instances`` accepts that record type).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.engine.evaluator import available_transitions as allowed_actions
from aip.modules.approvals.errors import NoActiveDefinitionError
from aip.modules.approvals.guards.context_providers import (
    GuardContextProvider,
    RecordRef,
    RecordResolver,
    register_guard_context_provider,
    register_record_resolver,
    unregister_guard_context_provider,
    unregister_record_resolver,
)
from aip.modules.approvals.guards.jsonlogic import (
    ALLOWED_OPERATORS,
    GuardError,
    evaluate_guard,
    truthy,
    validate_guard,
)
from aip.modules.approvals.presets import PresetError
from aip.modules.approvals.schemas import (
    StateSpec,
    TransitionSpec,
    WorkflowDefinition,
    WorkflowDefinitionSpec,
    WorkflowInstance,
)
from aip.modules.approvals.service import DefinitionsService, InstancesService
from aip.modules.approvals.transition import (
    Actor,
    Availability,
    History,
    InstanceView,
    TransitionResult,
    TransitionService,
)
from aip.platform.access import PolicyService

__all__ = [
    "ALLOWED_OPERATORS",
    "Actor",
    "ApprovalsApi",
    "Availability",
    "GuardContextProvider",
    "GuardError",
    "History",
    "InstanceView",
    "NoActiveDefinitionError",
    "PresetError",
    "RecordRef",
    "RecordResolver",
    "StateSpec",
    "TransitionResult",
    "TransitionSpec",
    "WorkflowDefinition",
    "WorkflowDefinitionSpec",
    "WorkflowInstance",
    "allowed_actions",
    "evaluate_guard",
    "register_guard_context_provider",
    "register_record_resolver",
    "truthy",
    "unregister_guard_context_provider",
    "unregister_record_resolver",
    "validate_guard",
]

_definitions = DefinitionsService()
_instances = InstancesService(_definitions)


class ApprovalsApi:
    """The operations the approvals module offers to other modules."""

    async def get_or_start_instance(
        self, conn: AsyncConnection, record_type: str, record_id: UUID, project_id: UUID | None
    ) -> WorkflowInstance:
        """The record's workflow instance, started on the active definition if it has none.

        No permission check: for a host module that has already authorised the record's creation.
        """
        return await _instances.start_instance(conn, record_type, record_id, project_id)

    async def get_active_definition(
        self, conn: AsyncConnection, record_type: str, project_id: UUID | None = None
    ) -> WorkflowDefinition:
        """The project's active definition for ``record_type``, else the tenant-wide one."""
        return await _definitions.get_active_definition(conn, record_type, project_id)

    async def install_preset(
        self, conn: AsyncConnection, preset_key: str, *, project_id: UUID | None = None
    ) -> WorkflowDefinition:
        """Publish the ``config/workflows`` preset ``preset_key`` idempotently (APPROVALS-08).

        Host modules (issues, inspections) ship their lifecycle as data and call this to install
        it. Returns the active definition unchanged when it already matches the preset.
        """
        return await _definitions.install_preset(conn, preset_key, project_id=project_id)

    async def start_instance(
        self,
        conn: AsyncConnection,
        policy: PolicyService,
        actor: Actor,
        record_type: str,
        record_id: UUID,
        project_id: UUID | None,
    ) -> InstanceView:
        """Start (or return) the record's instance, checking ``approvals.start``."""
        service = TransitionService(policy, _instances)
        return await service.start(conn, actor, record_type, record_id, project_id)

    async def transition(
        self,
        conn: AsyncConnection,
        policy: PolicyService,
        actor: Actor,
        instance_id: UUID,
        action: str,
        *,
        comment: str | None = None,
        expected_sync_version: int | None = None,
    ) -> TransitionResult:
        """Take ``action``: the same path as ``POST /approvals/instances/{id}/transition``."""
        return await TransitionService(policy, _instances).transition(
            conn,
            actor,
            instance_id,
            action,
            comment=comment,
            expected_sync_version=expected_sync_version,
        )

    async def available_transitions(
        self, conn: AsyncConnection, policy: PolicyService, actor: Actor, instance_id: UUID
    ) -> InstanceView:
        """The instance and what ``actor`` may do next (``allowed``/``reason_key`` each)."""
        return await TransitionService(policy, _instances).describe(conn, actor, instance_id)

    async def get_history(
        self, conn: AsyncConnection, policy: PolicyService, actor: Actor, instance_id: UUID
    ) -> History:
        """Every decision on the instance and whether its hash chain holds."""
        return await TransitionService(policy, _instances).history(conn, actor, instance_id)
