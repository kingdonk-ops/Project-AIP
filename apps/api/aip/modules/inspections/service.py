"""Inspection use cases (INSPECTIONS-01): create, transition, re-inspect, read and list.

Every function takes the caller's ``with_tenant`` connection, so the inspection row, its workflow
instance and its outbox events land in one transaction: any failure writes none of them. Other
modules are reached only through their ``api.py`` (ADR 0004): assets and projects for existence,
forms for the pinned revision, approvals for the lifecycle.

Permissions are checked here against the inspection's project (the ADR 0035 §6 pattern: a
project-scoped grant needs the loaded record). A lifecycle move is checked by the approvals
transition service (``approvals.view`` plus the transition's ``requiredPermission``, guard,
sign-off assurance and the hash-chained decision); its errors pass through unchanged.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.approvals.api import (
    Actor,
    ApprovalsApi,
    History,
    InstanceView,
    NoActiveDefinitionError,
    TransitionResult,
)
from aip.modules.assets.api import AssetsApi
from aip.modules.forms.api import FormRevisionOut, FormsApi
from aip.modules.inspections import repository as repo
from aip.modules.inspections.events import INSPECTION_CREATED, INSPECTION_STATE_CHANGED
from aip.modules.inspections.policies import (
    CREATE_PERMISSION,
    RECORD_TYPE,
    VIEW_PERMISSION,
    can_reinspect,
)
from aip.modules.projects.api import ProjectsApi
from aip.platform.access import PolicyService, Resource
from aip.platform.context import new_request_id
from aip.platform.db.errors import NotFoundError
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = [
    "MESSAGE_KEYS",
    "InspectionService",
    "NewInspection",
    "Page",
    "current_state",
    "sync_state",
]

# The error codes this module raises and the term key of each message (config/terms).
MESSAGE_KEYS: Final[dict[str, str]] = {
    "ASSET_NOT_FOUND": "inspection.error.asset_not_found",
    "TEMPLATE_NOT_PUBLISHED": "inspection.error.template_not_published",
    "REVISION_MISMATCH": "inspection.error.revision_mismatch",
    "NO_INSPECTION_WORKFLOW": "inspection.error.no_inspection_workflow",
    "NOT_COMPLETED": "inspection.error.not_completed",
}

_approvals = ApprovalsApi()
_assets = AssetsApi()
_forms = FormsApi()
_projects = ProjectsApi()


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _error(status_code: int, code: str) -> DomainError:
    return DomainError(status_code, code, messageKey=MESSAGE_KEYS[code])


@dataclass(frozen=True, slots=True)
class NewInspection:
    """What a create needs; the server, never a client, sets ``source`` and ``source_ref_id``."""

    asset_id: UUID
    template_id: UUID
    kind: str
    project_id: UUID | None = None
    template_revision_id: UUID | None = None
    source: str = "manual"
    source_ref_id: UUID | None = None
    client_generated_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Page:
    items: list[dict[str, Any]]
    next_cursor: str | None


def _encode_cursor(row: dict[str, Any]) -> str:
    body = json.dumps({"createdAt": row["created_at"].isoformat(), "id": str(row["id"])})
    return base64.urlsafe_b64encode(body.encode()).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """The position a cursor names. Cursors are opaque but not signed: a forged one only moves
    the page start, never past RLS or the caller's project filter."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        data = json.loads(raw)
        return datetime.fromisoformat(data["createdAt"]), UUID(data["id"])
    except (binascii.Error, ValueError, KeyError, TypeError):
        raise DomainError(422, "INVALID_CURSOR", field="cursor") from None


async def _pin_revision(conn: AsyncConnection, data: NewInspection) -> FormRevisionOut:
    """The form revision a new inspection pins: the named published one, else the current."""
    if data.template_revision_id is None:
        revision = await _forms.get_current_revision(conn, data.template_id)
        if revision is None:
            raise _error(422, "TEMPLATE_NOT_PUBLISHED")
        return revision
    revision = await _forms.get_revision(conn, data.template_revision_id)
    if (
        revision is None
        or revision.status != "published"
        or revision.template_id != data.template_id
    ):
        raise _error(422, "REVISION_MISMATCH")
    return revision


async def _emit_state_changed(
    conn: AsyncConnection, row: dict[str, Any], to_state: str, action: str
) -> None:
    payload = {
        "inspectionId": str(row["id"]),
        "assetId": str(row["asset_id"]),
        "projectId": None if row["project_id"] is None else str(row["project_id"]),
        "from": row["state"],
        "to": to_state,
        "action": action,
    }
    await emit(
        conn,
        INSPECTION_STATE_CHANGED,
        1,
        Aggregate(RECORD_TYPE, row["id"]),
        payload,
        asset_id=row["asset_id"],
    )


async def current_state(conn: AsyncConnection, row: dict[str, Any]) -> str:
    """The inspection's instance ``current_state`` (the truth; ``row["state"]`` is a cache)."""
    instance = await _approvals.get_or_start_instance(
        conn, RECORD_TYPE, row["id"], row["project_id"]
    )
    return instance.current_state


async def sync_state(conn: AsyncConnection, inspection_id: UUID, action: str) -> None:
    """Bring the cached ``state`` up to the instance's, emitting ``inspection.state_changed`` once.

    For the ``workflow.transitioned`` subscriber: idempotent, and a no-op when the inspection is
    gone or its state already matches (a transition taken through this module's route).
    """
    row = await repo.lock_inspection(conn, inspection_id)
    if row is None:
        return
    state = await current_state(conn, row)
    if state == row["state"]:
        return
    await repo.set_state(conn, inspection_id, state)
    await _emit_state_changed(conn, row, state, action)


class InspectionService:
    """Stateless apart from the policy service; the connection carries the tenant."""

    def __init__(self, policy: PolicyService) -> None:
        self._policy = policy

    async def _load(self, conn: AsyncConnection, inspection_id: UUID) -> dict[str, Any]:
        row = await repo.get_inspection(conn, inspection_id)
        if row is None:  # another tenant's (RLS) or an unknown id: 404 before any permission
            raise NotFoundError(f"inspection {inspection_id} not found")
        return row

    async def _load_viewable(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> dict[str, Any]:
        row = await self._load(conn, inspection_id)
        resource = Resource(project_id=row["project_id"])
        await self._policy.assert_can(actor.principal, VIEW_PERMISSION, resource)
        return row

    async def create(
        self, conn: AsyncConnection, actor: Actor, data: NewInspection
    ) -> tuple[dict[str, Any], bool]:
        """Create one inspection in ``draft``; ``(row, False)`` for an idempotent replay."""
        if data.source in ("scope_task", "reinspection") and data.source_ref_id is None:
            raise ValueError(f"an inspection from {data.source} needs source_ref_id")
        resource = Resource(project_id=data.project_id)
        await self._policy.assert_can(actor.principal, CREATE_PERMISSION, resource)  # (a)
        if data.client_generated_id is not None:
            existing = await repo.find_by_client_generated_id(conn, data.client_generated_id)
            if existing is not None:
                return existing, False
        try:  # (b)
            await _assets.assert_asset_exists(conn, data.asset_id)
        except NotFoundError:
            raise _error(404, "ASSET_NOT_FOUND") from None
        if data.project_id is not None:
            await _projects.assert_project_exists(conn, data.project_id)
        revision = await _pin_revision(conn, data)  # (c)

        inspection_id = _new_id()
        # A savepoint: a create that loses a client_generated_id race drops the instance it
        # started, so the first create's row and instance stand alone.
        savepoint = await conn.begin_nested()
        try:
            try:  # (e) before (d): the row stores the instance it runs on
                instance = await _approvals.get_or_start_instance(
                    conn, RECORD_TYPE, inspection_id, data.project_id
                )
            except NoActiveDefinitionError:
                raise _error(422, "NO_INSPECTION_WORKFLOW") from None
            result = await repo.insert_inspection(  # (d)
                conn,
                {
                    "id": inspection_id,
                    "tenant_id": actor.principal.tenant_id,
                    "asset_id": data.asset_id,
                    "project_id": data.project_id,
                    "template_id": data.template_id,
                    "template_revision_id": revision.id,
                    "kind": data.kind,
                    "source": data.source,
                    "source_ref_id": data.source_ref_id,
                    "workflow_instance_id": instance.id,
                    "state": instance.current_state,
                    "created_by": actor.principal.actor_id,
                    "client_generated_id": data.client_generated_id,
                },
            )
        except BaseException:
            await savepoint.rollback()
            raise
        if not result.created:
            await savepoint.rollback()
            return result.row, False
        await savepoint.commit()

        row = result.row
        payload = {  # (f)
            "inspectionId": str(row["id"]),
            "assetId": str(row["asset_id"]),
            "projectId": None if row["project_id"] is None else str(row["project_id"]),
            "kind": row["kind"],
            "templateRevisionId": str(row["template_revision_id"]),
            "source": row["source"],
        }
        await emit(
            conn,
            INSPECTION_CREATED,
            1,
            Aggregate(RECORD_TYPE, row["id"]),
            payload,
            asset_id=row["asset_id"],
        )
        return row, True

    async def transition(
        self,
        conn: AsyncConnection,
        actor: Actor,
        inspection_id: UUID,
        action: str,
        *,
        comment: str | None = None,
        expected_sync_version: int | None = None,
    ) -> tuple[dict[str, Any], TransitionResult]:
        """Take ``action`` through the approvals transition service; follow it when applied."""
        row = await repo.lock_inspection(conn, inspection_id)
        if row is None:
            raise NotFoundError(f"inspection {inspection_id} not found")
        result = await _approvals.transition(
            conn,
            self._policy,
            actor,
            row["workflow_instance_id"],
            action,
            comment=comment,
            expected_sync_version=expected_sync_version,
        )
        if result.applied:
            to_state = str(result.view.instance["current_state"])
            if to_state != row["state"]:
                updated = await repo.set_state(conn, inspection_id, to_state)
                await _emit_state_changed(conn, row, to_state, action)
                row = updated
        return row, result

    async def reinspect(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> dict[str, Any]:
        """A new ``draft`` inspection of the same asset, project, template and kind, on the
        template's current published revision (APPROVALS-09: re-inspection starts from
        ``performed``; superseding the original is INSPECTIONS-09)."""
        source = await repo.lock_inspection(conn, inspection_id)
        if source is None:
            raise NotFoundError(f"inspection {inspection_id} not found")
        resource = Resource(project_id=source["project_id"])
        await self._policy.assert_can(actor.principal, CREATE_PERMISSION, resource)
        if not can_reinspect(await current_state(conn, source)):
            raise _error(409, "NOT_COMPLETED")
        row, _ = await self.create(
            conn,
            actor,
            NewInspection(
                asset_id=source["asset_id"],
                template_id=source["template_id"],
                kind=source["kind"],
                project_id=source["project_id"],
                source="reinspection",
                source_ref_id=source["id"],
            ),
        )
        return row

    async def describe(
        self, conn: AsyncConnection, actor: Actor, inspection_id: UUID
    ) -> tuple[dict[str, Any], InstanceView]:
        """The inspection and its workflow as ``actor`` sees it (``inspection.view``)."""
        row = await self._load_viewable(conn, actor, inspection_id)
        view = await _approvals.available_transitions(
            conn, self._policy, actor, row["workflow_instance_id"]
        )
        return row, view

    async def history(self, conn: AsyncConnection, actor: Actor, inspection_id: UUID) -> History:
        row = await self._load_viewable(conn, actor, inspection_id)
        return await _approvals.get_history(conn, self._policy, actor, row["workflow_instance_id"])

    async def list(
        self,
        conn: AsyncConnection,
        actor: Actor,
        filters: repo.Filters,
        *,
        limit: int,
        cursor: str | None,
    ) -> Page:
        """Live inspections newest first, limited to projects the caller may view."""
        after = None if cursor is None else _decode_cursor(cursor)
        principal = actor.principal
        if not (await self._policy.can(principal, VIEW_PERMISSION, Resource())).allowed:
            # No tenant-wide grant: only inspections on projects the caller holds the view on.
            project_ids = await self._policy.filter_allowed(
                principal,
                VIEW_PERMISSION,
                await _projects.list_project_ids(conn),
                lambda project_id: Resource(project_id=project_id),
            )
            filters = replace(filters, project_ids=project_ids)
        rows = await repo.list_inspections(conn, filters, limit, after)
        next_cursor = _encode_cursor(rows[limit - 1]) if len(rows) > limit else None
        return Page(items=rows[:limit], next_cursor=next_cursor)
