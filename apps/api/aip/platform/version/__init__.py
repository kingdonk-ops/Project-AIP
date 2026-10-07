"""Platform version endpoint (STACK-05), mounted by ``aip.main`` under ``/api/v1``."""

from aip.platform.version.routes import Dependencies, VersionResponse, router

__all__ = ["Dependencies", "VersionResponse", "router"]
