"""The ``ensure_partitions`` periodic job (DATABASE-05, ADR 0003).

Every day at 02:17 UTC it calls ``aip_ensure_partitions(table_name, months_ahead)`` for each row
of ``partition_settings``, as ``aip_jobs`` (the only role allowed to execute it), then checks with
``missing_partitions`` that this month's and the next ``months_ahead`` months' partitions exist.

A failing table does not stop the others. Each failure is logged at ERROR with
``db_partition_create_failed`` in the message and counted on the OpenTelemetry counter of the
same name (alerting is wired by ops); after all tables, the job raises
``PartitionMaintenanceError`` so Procrastinate records the run as failed.

The worker imports this module (``aip.worker``); the migrator image never does.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime

from opentelemetry import metrics
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aip.platform.db.engine import get_jobs_engine
from aip.platform.db.partitions import missing_partitions
from aip.platform.jobs.app import DEFAULT_QUEUE, app

__all__ = [
    "FAILURE_METRIC",
    "PartitionMaintenanceError",
    "ensure_all_partitions",
    "ensure_partitions",
]

logger = logging.getLogger(__name__)

FAILURE_METRIC = "db_partition_create_failed"
_failures = metrics.get_meter(__name__).create_counter(
    FAILURE_METRIC, description="Append-only tables whose monthly partitions could not be ensured"
)

_SETTINGS = text("SELECT table_name, months_ahead FROM partition_settings ORDER BY table_name")
_ENSURE = text("SELECT name FROM aip_ensure_partitions(:table, :months_ahead) AS name")
_EXISTING = text(
    "SELECT c.relname FROM pg_inherits AS h JOIN pg_class AS c ON c.oid = h.inhrelid "
    "WHERE h.inhparent = to_regclass(:table)"
)


class PartitionMaintenanceError(RuntimeError):
    """One or more tables in ``partition_settings`` could not be given their partitions."""


def _record_failure(attributes: Mapping[str, str]) -> None:
    _failures.add(1, attributes)


async def _ensure_one(engine: AsyncEngine, table: str, months_ahead: int, today: date) -> list[str]:
    async with engine.begin() as conn:
        created = list(
            (await conn.execute(_ENSURE, {"table": table, "months_ahead": months_ahead})).scalars()
        )
        existing = set((await conn.execute(_EXISTING, {"table": f"public.{table}"})).scalars())
    missing = missing_partitions(existing, today, months_ahead, table=table)
    if missing:
        raise PartitionMaintenanceError(f"{table}: still missing {', '.join(missing)}")
    return created


async def ensure_all_partitions(
    engine: AsyncEngine, *, today: date | None = None
) -> dict[str, list[str]]:
    """Ensure partitions for every table in ``partition_settings``; returns the names created.

    ``engine`` must connect as ``aip_jobs``. Each table runs in its own transaction.
    """
    today = today or datetime.now(UTC).date()
    async with engine.begin() as conn:
        settings = [(str(r[0]), int(r[1])) for r in (await conn.execute(_SETTINGS)).all()]
    created: dict[str, list[str]] = {}
    failed: list[str] = []
    for table, months_ahead in settings:
        try:
            created[table] = await _ensure_one(engine, table, months_ahead, today)
        except Exception:
            failed.append(table)
            logger.exception("%s: could not ensure partitions of %s", FAILURE_METRIC, table)
            _record_failure({"table": table})
    if failed:
        raise PartitionMaintenanceError(f"partitions not ensured for: {', '.join(failed)}")
    return created


@app.periodic(cron="17 2 * * *", periodic_id="ensure_partitions")
@app.task(name="db.ensure_partitions", queue=DEFAULT_QUEUE)
async def ensure_partitions(timestamp: int) -> None:
    """Procrastinate entry point; ``timestamp`` is the scheduled time Procrastinate passes."""
    created = await ensure_all_partitions(get_jobs_engine())
    logger.info("partitions ensured: %s", created)
