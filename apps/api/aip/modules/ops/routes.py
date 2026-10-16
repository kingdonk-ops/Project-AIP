"""Registry entry point for the ops module (ARCH-02).

The health probes in ``health.py`` are mounted directly by ``aip.main`` so that disabling modules
can never remove them (OPS-04). The registry mounts only the operator API for tenant entitlements
(``platform_tenants``, ENT-01) and the jobs API (``jobs_routes``, OPS-03).
"""

from fastapi import APIRouter

from aip.modules.ops.jobs_routes import router as jobs_router
from aip.modules.ops.platform_tenants import router as platform_tenants_router

router = APIRouter()
router.include_router(platform_tenants_router)
router.include_router(jobs_router)
