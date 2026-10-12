"""Business logic for access (ACCESS-01).

``sync_catalogue`` mirrors the app's permission catalogue into the global ``permission`` table.
``aip.main`` calls it once from the lifespan startup hook. Without ``DATABASE_URL`` (unit tests,
the e2e API) there is nothing to sync and it only logs; a database error stops startup, so the
table never silently drifts from the manifests.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.modules.access import repository as repo
from aip.platform.access import Catalogue
from aip.platform.db.engine import DATABASE_URL_ENV
from aip.platform.db.session import before_tenant

__all__ = ["sync_catalogue"]

logger = logging.getLogger(__name__)

Connect = Callable[[], AbstractAsyncContextManager[AsyncConnection]]


async def sync_catalogue(catalogue: Catalogue, connect: Connect | None = None) -> bool:
    """Upsert the catalogue and deprecate removed codes. False when no database is configured."""
    if connect is None:
        if not os.environ.get(DATABASE_URL_ENV):
            logger.warning("%s is not set; permission catalogue not synced", DATABASE_URL_ENV)
            return False
        connect = before_tenant
    async with connect() as conn:
        await repo.sync_permissions(conn, catalogue.sync_payload())
    logger.info("permission catalogue synced (%d codes)", len(catalogue))
    return True
