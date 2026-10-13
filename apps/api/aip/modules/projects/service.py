"""Business logic for projects and sites (PROJECTS-01).

Every operation runs in one ``with_tenant(get_context())`` transaction, so the outbox event
commits or rolls back with the change. Rows of another tenant are invisible under RLS and come
back as 404, never 403.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.projects import repository as repo
from aip.modules.projects.cursor import CursorCodec, InvalidCursorError
from aip.modules.projects.events import PROJECT_ARCHIVED, PROJECT_CREATED, PROJECT_UPDATED
from aip.modules.projects.policies import can_transition
from aip.modules.projects.schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectPage,
    ProjectSort,
    ProjectStatus,
    ProjectUpdate,
    SiteCreate,
    SiteOut,
    SitePage,
    SiteUpdate,
)
from aip.modules.projects.settings import get_settings
from aip.modules.projects.tables import projects, sites
from aip.modules.tenancy.api import region_exists
from aip.platform.context import get_context, new_request_id
from aip.platform.db.errors import ConflictError, NotFoundError
from aip.platform.db.session import with_tenant
from aip.platform.events import Aggregate, emit
from aip.platform.http import DomainError

__all__ = ["ProjectService", "SiteService", "cursor_codec"]

_UNIQUE_VIOLATION: Final = "23505"
# Newest first for updated_at; alphabetical for code and name.
_DESCENDING: Final[frozenset[str]] = frozenset({"updated_at"})


def cursor_codec() -> CursorCodec:
    return CursorCodec(get_settings().cursor_key.get_secret_value().encode())


def _new_id() -> UUID:
    return UUID(new_request_id())  # the platform's UUIDv7 generator


def _invalid(code: str, field: str) -> DomainError:
    return DomainError(422, code, field=field)


@asynccontextmanager
async def _tx() -> AsyncIterator[AsyncConnection]:
    async with with_tenant(get_context()) as conn:
        yield conn


@asynccontextmanager
async def _unique(code: str) -> AsyncIterator[None]:
    """Turn a unique violation (the per-tenant code index) into a 409 with ``code``."""
    try:
        yield
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == _UNIQUE_VIOLATION:
            raise DomainError(409, code) from None
        raise


def _page(cursor: str | None, sort: str, limit: int) -> repo.Page:
    after: tuple[Any, UUID] | None = None
    if cursor is not None:
        try:
            data = cursor_codec().decode(cursor)
            if data.get("sort") != sort:
                raise InvalidCursorError("cursor was issued for another sort order")
            value = data["value"]
            if sort == "updated_at":
                value = datetime.fromisoformat(value)
            after = (value, UUID(data["id"]))
        except (InvalidCursorError, KeyError, TypeError, ValueError):
            raise _invalid("INVALID_CURSOR", "cursor") from None
    return repo.Page(sort=sort, descending=sort in _DESCENDING, limit=limit, after=after)


def _next_cursor(rows: list[dict[str, Any]], page: repo.Page) -> str | None:
    if len(rows) <= page.limit:
        return None
    last = rows[page.limit - 1]
    value = last[page.sort]
    if isinstance(value, datetime):
        value = value.isoformat()
    return cursor_codec().encode({"sort": page.sort, "value": value, "id": str(last["id"])})


async def _check_region(conn: AsyncConnection, region: str | None) -> None:
    if region is not None and not await region_exists(conn, region):
        raise _invalid("REGION_UNKNOWN", "region")


async def _check_site(conn: AsyncConnection, site_id: UUID | None) -> None:
    """The site must be live in this tenant; its row stays locked against deletion until commit."""
    if site_id is not None and not await repo.lock_live_site(conn, site_id, exclusive=False):
        raise _invalid("SITE_NOT_FOUND", "siteId")


def _camel(fields: Iterable[str], row: dict[str, Any]) -> dict[str, Any]:
    out = ProjectOut.model_validate(row).model_dump(mode="json", by_alias=True)
    names = {name: ProjectOut.model_fields[name].alias or name for name in fields}
    return {alias: out[alias] for alias in names.values()}


class ProjectService:
    async def list(
        self,
        *,
        limit: int,
        cursor: str | None,
        sort: ProjectSort,
        statuses: list[ProjectStatus],
        site_id: UUID | None,
        q: str | None,
    ) -> ProjectPage:
        page = _page(cursor, sort, limit)
        filters = []
        if statuses:
            filters.append(projects.c.status.in_(statuses))
        if site_id is not None:
            filters.append(projects.c.site_id == site_id)
        if q:
            filters.append(repo.search(projects, q))
        async with _tx() as conn:
            rows = await repo.list_page(conn, projects, page, *filters)
        items = [ProjectOut.model_validate(r) for r in rows[: page.limit]]
        return ProjectPage(items=items, next_cursor=_next_cursor(rows, page))

    async def get(self, project_id: UUID) -> ProjectOut:
        async with _tx() as conn:
            row = await repo.get_project(conn, project_id)
        if row is None:
            raise NotFoundError(f"project {project_id} not found")
        return ProjectOut.model_validate(row)

    async def create(self, body: ProjectCreate) -> ProjectOut:
        values = body.model_dump()
        async with _tx() as conn, _unique("PROJECT_CODE_TAKEN"):
            await _check_region(conn, body.region)
            await _check_site(conn, body.site_id)
            row = await repo.insert_project(
                conn, {**values, "id": _new_id(), "tenant_id": get_context().tenant_id}
            )
            project = ProjectOut.model_validate(row)
            await emit(conn, PROJECT_CREATED, 1, Aggregate("project", project.id), _payload(row))
        return project

    async def update(self, project_id: UUID, body: ProjectUpdate) -> ProjectOut:
        patch = body.changes(exclude=frozenset({"sync_version"}))
        async with _tx() as conn, _unique("PROJECT_CODE_TAKEN"):
            current = await repo.get_project(conn, project_id)
            if current is None:
                raise NotFoundError(f"project {project_id} not found")
            if current["sync_version"] != body.sync_version:
                raise ConflictError(_out(current))
            new_status = patch.get("status", current["status"])
            if new_status == current["status"]:
                patch.pop("status", None)
            elif not can_transition(current["status"], new_status):
                raise DomainError(
                    409,
                    "INVALID_STATUS_TRANSITION",
                    current=current["status"],
                    requested=new_status,
                )
            if new_status == "archived" and "status" in patch:
                patch["closed_at"] = datetime.now(UTC)
            if "region" in patch:
                await _check_region(conn, patch["region"])
            if "site_id" in patch:
                await _check_site(conn, patch["site_id"])
            changed = [f for f, v in patch.items() if current[f] != v]
            if not changed:
                return ProjectOut.model_validate(current)
            try:
                row = await repo.update_project(
                    conn, project_id, body.sync_version, {f: patch[f] for f in changed}
                )
            except ConflictError as exc:  # another writer won between our read and write
                raise ConflictError(_out(dict(exc.current))) from None
            payload = _payload(row, before=_camel(changed, current), after=_camel(changed, row))
            aggregate = Aggregate("project", project_id)
            await emit(conn, PROJECT_UPDATED, 1, aggregate, payload)
            if "status" in changed and row["status"] == "archived":
                await emit(conn, PROJECT_ARCHIVED, 1, aggregate, payload)
        return ProjectOut.model_validate(row)


def _out(row: dict[str, Any]) -> dict[str, Any]:
    """A row as the API shows it (camelCase), for the 409 ``current`` body."""
    return ProjectOut.model_validate(row).model_dump(mode="json", by_alias=True)


def _payload(
    row: dict[str, Any],
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "projectId": str(row["id"]),
        "code": row["code"],
        "status": row["status"],
    }
    if before is not None:
        payload["before"] = before
    if after is not None:
        payload["after"] = after
    return payload


class SiteService:
    async def list(self, *, limit: int, cursor: str | None, q: str | None) -> SitePage:
        page = _page(cursor, "code", limit)
        filters = [repo.search(sites, q)] if q else []
        async with _tx() as conn:
            rows = await repo.list_page(conn, sites, page, *filters)
        items = [SiteOut.model_validate(r) for r in rows[: page.limit]]
        return SitePage(items=items, next_cursor=_next_cursor(rows, page))

    async def get(self, site_id: UUID) -> SiteOut:
        async with _tx() as conn:
            row = await repo.get_site(conn, site_id)
        if row is None:
            raise NotFoundError(f"site {site_id} not found")
        return SiteOut.model_validate(row)

    async def create(self, body: SiteCreate) -> SiteOut:
        values = {**body.model_dump(), "id": _new_id(), "tenant_id": get_context().tenant_id}
        async with _tx() as conn, _unique("SITE_CODE_TAKEN"):
            row = await repo.insert_site(conn, values)
        return SiteOut.model_validate(row)

    async def update(self, site_id: UUID, body: SiteUpdate) -> SiteOut:
        patch = body.changes()
        async with _tx() as conn, _unique("SITE_CODE_TAKEN"):
            if patch:
                row = await repo.update_site(conn, site_id, patch)
            else:
                row = await repo.get_site(conn, site_id)
        if row is None:
            raise NotFoundError(f"site {site_id} not found")
        return SiteOut.model_validate(row)

    async def delete(self, site_id: UUID) -> None:
        async with _tx() as conn:
            if not await repo.lock_live_site(conn, site_id, exclusive=True):
                raise NotFoundError(f"site {site_id} not found")
            if await repo.site_in_use(conn, site_id):
                raise DomainError(409, "SITE_IN_USE")
            await repo.delete_site(conn, site_id)
