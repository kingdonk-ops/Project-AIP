"""Business logic for organisations (TENANCY-03).

Every operation runs in one ``with_tenant(get_context())`` transaction, so the outbox event
commits or rolls back with the change. Another tenant's organisation is invisible under RLS and
comes back as 404, never 403. Deactivating is ``status = inactive``; rows are never deleted here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.tenancy.events import ORGANISATION_CREATED, ORGANISATION_UPDATED
from aip.modules.tenancy.organisations import repository as repo
from aip.modules.tenancy.organisations.schemas import (
    OrganisationCreate,
    OrganisationList,
    OrganisationOut,
    OrganisationStatus,
    OrganisationType,
    OrganisationUpdate,
)
from aip.platform.context import get_context, new_request_id
from aip.platform.db.errors import ConflictError, NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = ["OrganisationService"]

_UNIQUE_VIOLATION: Final = "23505"
NAME_TAKEN: Final = "ORGANISATION_NAME_TAKEN"


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


@asynccontextmanager
async def _unique_name() -> AsyncIterator[None]:
    """Turn a unique violation (the per-tenant name index) into 409 ``ORGANISATION_NAME_TAKEN``."""
    try:
        yield
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION:
            raise DomainError(409, NAME_TAKEN) from None
        raise


def _out(row: dict[str, Any]) -> dict[str, Any]:
    """A row as the API shows it (camelCase)."""
    return OrganisationOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _subset(fields: list[str], row: dict[str, Any]) -> dict[str, Any]:
    out = _out(row)
    aliases = [OrganisationOut.model_fields[f].alias or f for f in fields]
    return {alias: out[alias] for alias in aliases}


def _payload(
    row: dict[str, Any],
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "organisationId": str(row["id"]),
        "name": row["name"],
        "type": row["org_type"],
        "status": row["status"],
        "before": before,
        "after": after,
    }


class OrganisationService:
    async def list(
        self, *, types: list[OrganisationType], statuses: list[OrganisationStatus]
    ) -> OrganisationList:
        async with _tx() as conn:
            rows = await repo.list_live(conn, types=types, statuses=statuses)
        return OrganisationList(items=[OrganisationOut.model_validate(r) for r in rows])

    async def get(self, organisation_id: UUID) -> OrganisationOut:
        async with _tx() as conn:
            row = await repo.get(conn, organisation_id)
        if row is None:
            raise NotFoundError(f"organisation {organisation_id} not found")
        return OrganisationOut.model_validate(row)

    async def create(self, body: OrganisationCreate) -> OrganisationOut:
        values = {
            **body.model_dump(),
            "id": UUID(new_request_id()),  # the platform's UUIDv7 generator
            "tenant_id": get_context().tenant_id,
        }
        async with _tx() as conn, _unique_name():
            row = await repo.insert_one(conn, values)
            aggregate = Aggregate("organisation", row["id"])
            await emit(conn, ORGANISATION_CREATED, 1, aggregate, _payload(row))
        return OrganisationOut.model_validate(row)

    async def update(self, organisation_id: UUID, body: OrganisationUpdate) -> OrganisationOut:
        patch = body.changes(exclude=frozenset({"sync_version"}))
        async with _tx() as conn, _unique_name():
            current = await repo.get(conn, organisation_id)
            if current is None:
                raise NotFoundError(f"organisation {organisation_id} not found")
            if current["sync_version"] != body.sync_version:
                raise ConflictError(_out(current))
            changed = [f for f, v in patch.items() if current[f] != v]
            if not changed:
                return OrganisationOut.model_validate(current)
            try:
                row = await repo.update(
                    conn, organisation_id, body.sync_version, {f: patch[f] for f in changed}
                )
            except ConflictError as exc:  # another writer won between our read and write
                raise ConflictError(_out(dict(exc.current))) from None
            payload = _payload(row, before=_subset(changed, current), after=_subset(changed, row))
            aggregate = Aggregate("organisation", organisation_id)
            await emit(conn, ORGANISATION_UPDATED, 1, aggregate, payload)
        return OrganisationOut.model_validate(row)
