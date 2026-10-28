"""Workflow definitions and instances (APPROVALS-01).

Every method runs on the caller's ``with_tenant`` connection, so it commits or rolls back with the
caller's change and RLS keeps each tenant to its own rows. ``created_by``/``actor_id`` come from the
request context (``None`` outside a request, e.g. in a seed job), never from the caller.

- ``create_draft`` makes version ``max(version) + 1`` of a key (versions count up per key, across
  scopes), serialised per tenant and key by a transaction advisory lock.
- ``update_draft`` and ``publish`` work only on a ``draft``; ``DefinitionImmutableError`` otherwise.
- ``publish`` retires the active version of the same key and scope (tenant-wide or one project),
  activates the draft, writes the ``{before, after}`` audit row and emits
  ``workflow.definition_published`` v1 (APPROVALS-02), all in the caller's transaction. Emitting
  needs a request context.
- ``get_active_definition`` prefers the project's definition, then the tenant-wide one.
- ``start_instance`` pins the instance to the version active now; a second call for the same record
  returns the existing instance, so later publishes never move it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals import repository as repo
from aip.modules.approvals.errors import (
    DefinitionImmutableError,
    DefinitionNotFoundError,
    NoActiveDefinitionError,
)
from aip.modules.approvals.events import WORKFLOW_DEFINITION_PUBLISHED, DefinitionPublished
from aip.modules.approvals.presets import Preset, load_preset
from aip.modules.approvals.schemas import (
    WorkflowDefinition,
    WorkflowDefinitionSpec,
    WorkflowInstance,
    validate_spec,
)
from aip.platform.context import ContextMissingError, get_context, new_request_id
from aip.platform.events import Aggregate, emit

__all__ = ["DefinitionsService", "InstancesService", "definition_from_row", "new_id"]


def new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _actor() -> UUID | None:
    try:
        return get_context().actor_id
    except ContextMissingError:
        return None


def definition_from_row(row: RowMapping) -> WorkflowDefinition:
    spec = WorkflowDefinitionSpec.model_validate(
        {
            "states": row["states"],
            "transitions": row["transitions"],
            "initial": row["initial_state"],
        }
    )
    return WorkflowDefinition(
        id=row["id"],
        record_type=row["record_type"],
        project_id=row["project_id"],
        key=row["key"],
        version=row["version"],
        status=row["status"],
        spec=spec,
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _snapshot(definition: WorkflowDefinition) -> dict[str, Any]:
    return {
        "id": str(definition.id),
        "key": definition.key,
        "version": definition.version,
        "status": definition.status,
        "projectId": None if definition.project_id is None else str(definition.project_id),
        "spec": definition.spec.to_json(),
    }


async def _draft_for_update(conn: AsyncConnection, definition_id: UUID) -> WorkflowDefinition:
    row = await repo.get_definition_for_update(conn, definition_id)
    if row is None:
        raise DefinitionNotFoundError(f"workflow definition {definition_id} not found")
    definition = definition_from_row(row)
    if definition.status != "draft":
        raise DefinitionImmutableError(
            f"workflow definition {definition_id} is {definition.status}; only drafts change"
        )
    return definition


class DefinitionsService:
    """Stateless; the connection carries the tenant."""

    async def create_draft(
        self,
        conn: AsyncConnection,
        key: str,
        record_type: str,
        spec: object,
        project_id: UUID | None = None,
    ) -> WorkflowDefinition:
        """A new draft: the next version of ``key`` for ``record_type`` (and ``project_id``)."""
        checked = validate_spec(spec)
        await repo.lock_key(conn, key)
        version = await repo.next_version(conn, key)
        row = await repo.insert_definition(
            conn,
            id=new_id(),
            record_type=record_type,
            project_id=project_id,
            key=key,
            version=version,
            spec=checked.to_json(),
            created_by=_actor(),
        )
        return definition_from_row(row)

    async def update_draft(
        self, conn: AsyncConnection, definition_id: UUID, spec: object
    ) -> WorkflowDefinition:
        """Replace a draft's spec; an active or retired one raises ``DefinitionImmutableError``."""
        checked = validate_spec(spec)
        await _draft_for_update(conn, definition_id)
        return definition_from_row(await repo.update_spec(conn, definition_id, checked.to_json()))

    async def publish(self, conn: AsyncConnection, definition_id: UUID) -> WorkflowDefinition:
        """Activate a draft, retiring the active version of its key and scope, with an audit row."""
        draft = await _draft_for_update(conn, definition_id)
        await repo.lock_key(conn, draft.key)
        previous_row = await repo.active_in_scope_for_update(conn, draft.key, draft.project_id)
        before = None
        previous_id: UUID | None = None
        if previous_row is not None:
            previous = definition_from_row(previous_row)
            before = _snapshot(previous)
            previous_id = previous.id
            await repo.set_status(conn, previous.id, "retired")
        published = definition_from_row(await repo.set_status(conn, definition_id, "active"))
        await repo.insert_audit(
            conn,
            id=new_id(),
            definition_id=definition_id,
            actor_id=_actor(),
            change={"before": before, "after": _snapshot(published)},
        )
        payload = DefinitionPublished(
            definition_id=published.id,
            key=published.key,
            version=published.version,
            record_type=published.record_type,
            project_id=published.project_id,
            previous_definition_id=previous_id,
        ).model_dump(mode="json")
        await emit(
            conn,
            WORKFLOW_DEFINITION_PUBLISHED,
            1,
            Aggregate("workflow_definition", published.id),
            payload,
        )
        return published

    async def get_active_definition(
        self, conn: AsyncConnection, record_type: str, project_id: UUID | None = None
    ) -> WorkflowDefinition:
        """The project's active definition for ``record_type``, else the tenant-wide one."""
        row = await repo.resolve_active(conn, record_type, project_id)
        if row is None:
            raise NoActiveDefinitionError(f"no active workflow definition for {record_type}")
        return definition_from_row(row)

    async def install_preset(
        self,
        conn: AsyncConnection,
        preset_key: str,
        *,
        project_id: UUID | None = None,
        base_dir: Path | None = None,
    ) -> WorkflowDefinition:
        """Publish the ``config/workflows`` preset ``preset_key`` idempotently (APPROVALS-08).

        A host module ships its lifecycle as data and calls this to install it. When the active
        definition for the preset's key and scope already matches the preset spec, it is returned
        unchanged; otherwise a new draft is created and published (retiring the previous version),
        emitting ``workflow.definition_published`` like any other publish. ``PresetError`` for a bad
        preset, ``ValidationError`` for a spec that fails the graph rules.
        """
        preset: Preset = load_preset(preset_key, base_dir)
        return await self.install_spec(
            conn, preset.key, preset.record_type, preset.spec, project_id=project_id
        )

    async def install_spec(
        self,
        conn: AsyncConnection,
        key: str,
        record_type: str,
        spec: object,
        *,
        project_id: UUID | None = None,
    ) -> WorkflowDefinition:
        """Publish ``spec`` as ``key`` unless the active definition in that scope already matches.

        The idempotent core of :meth:`install_preset`, also used by the dev and demo seed for a
        workflow that is not a preset (TESTING-13).
        """
        checked = validate_spec(spec)
        current_row = await repo.active_in_scope_for_update(conn, key, project_id)
        if current_row is not None:
            current = definition_from_row(current_row)
            unchanged = (
                current.record_type == record_type
                and current.spec.to_json() == checked.to_json()
            )
            if unchanged:
                return current
        draft = await self.create_draft(conn, key, record_type, spec, project_id)
        return await self.publish(conn, draft.id)


class InstancesService:
    """Stateless; the connection carries the tenant."""

    def __init__(self, definitions: DefinitionsService | None = None) -> None:
        self._definitions = definitions or DefinitionsService()

    async def start_instance(
        self, conn: AsyncConnection, record_type: str, record_id: UUID, project_id: UUID | None
    ) -> WorkflowInstance:
        """The record's instance, starting one on the active definition if there is none yet."""
        existing = await repo.get_instance(conn, record_type, record_id)
        if existing is not None:
            return WorkflowInstance.model_validate(dict(existing))
        definition = await self._definitions.get_active_definition(conn, record_type, project_id)
        row = await repo.insert_instance(
            conn,
            id=new_id(),
            project_id=project_id,
            definition_id=definition.id,
            record_type=record_type,
            record_id=record_id,
            current_state=definition.spec.initial,
            created_by=_actor(),
        )
        return WorkflowInstance.model_validate(dict(row))
