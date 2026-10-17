"""Platform version endpoints (STACK-05), mounted by ``aip.main`` under ``/api/v1``."""

from aip.platform.version.routes import (
    Dependencies,
    VersionResponse,
    dependencies_router,
    router,
)

__all__ = ["Dependencies", "VersionResponse", "dependencies_router", "router"]
