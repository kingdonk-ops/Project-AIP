"""Published interface of the projects module (PROJECTS-01).

Other modules may import only this file. They pass the tenant-bound connection they already hold
from ``with_tenant``, so the project read joins their transaction and RLS applies.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.projects import repository as repo
from aip.modules.projects.schemas import ProjectOut
from aip.platform.db.errors import NotFoundError

__all__ = ["ProjectOut", "ProjectsApi"]


class ProjectsApi:
    """The operations the projects module offers to other modules."""

    async def get_project(self, conn: AsyncConnection, project_id: UUID) -> ProjectOut | None:
        """The live project ``project_id`` in the connection's tenant, or ``None``."""
        row = await repo.get_project(conn, project_id)
        return None if row is None else ProjectOut.model_validate(row)

    async def assert_project_exists(self, conn: AsyncConnection, project_id: UUID) -> None:
        """Raise ``NotFoundError`` (HTTP 404) unless the project is live in this tenant."""
        if await repo.get_project(conn, project_id) is None:
            raise NotFoundError(f"project {project_id} not found")

    async def list_project_ids(self, conn: AsyncConnection) -> list[UUID]:
        """The ids of every live project in the connection's tenant."""
        return await repo.list_project_ids(conn)
