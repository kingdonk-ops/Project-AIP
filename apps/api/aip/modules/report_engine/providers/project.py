"""The ``project`` report data provider (REPORTS-02).

Reads the project through ``aip.modules.projects.api.ProjectsApi`` on the caller's connection, so
another tenant's (or an out-of-scope) project is ``RecordNotFound``. The data is
``{project: {id, code, name, status, timezone, region, createdAt}}``; ``record_version`` is the
project's ``sync_version`` and the time-zone hint its ``timezone``. Viewing it needs
``project.view`` on that project.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.projects.api import ProjectsApi
from aip.modules.report_engine.providers import RecordNotFound, ReportSource, register_provider

__all__ = ["PROJECT_RECORD_TYPE", "install", "project_source"]

PROJECT_RECORD_TYPE: Final = "project"
_projects = ProjectsApi()


async def project_source(
    conn: AsyncConnection, record_id: UUID, *, context: Mapping[str, Any]
) -> ReportSource:
    del context  # a project report needs no trigger data
    project = await _projects.get_project(conn, record_id)
    if project is None:
        raise RecordNotFound(f"project {record_id}")
    plain = project.model_dump(mode="json", by_alias=False)  # JSON types: str ids and timestamps
    return ReportSource(
        project_id=project.id,
        record_version=project.sync_version,
        data={
            "project": {
                "id": plain["id"],
                "code": plain["code"],
                "name": plain["name"],
                "status": plain["status"],
                "timezone": plain["timezone"],
                "region": plain["region"],
                "createdAt": plain["created_at"],
            }
        },
        time_zone_hint=project.timezone,
    )


def install() -> None:
    """Register the provider (idempotent)."""
    register_provider(PROJECT_RECORD_TYPE, project_source, view_permission="project.view")
