"""The Procrastinate application: queue names, job locks, the atomic defer and the worker loop.

Procrastinate (MIT, Postgres-backed, asyncio; ADR 0003) carries the work; the user-visible record
is the OPS-01 ``jobs`` table. Nothing durable lives in Redis.

**Atomic enqueue.** ``defer_in_transaction`` calls Procrastinate's own defer SQL function
(``procrastinate_defer_jobs_v1``) on the caller's tenant-bound connection, so a rolled-back
transaction leaves neither a domain row, a ``jobs`` row nor a queue row. Procrastinate's own
``Task.defer`` would use a second connection and break that, so the API process never calls it.

**Workers** connect as ``aip_jobs`` (``DATABASE_JOBS_URL``) through Procrastinate's psycopg pool,
which is why this module lives in ``aip.platform.jobs`` and not in a module. Application data is
read and written by the job runner through ``with_tenant`` on the ``aip_jobs`` engine.

**Fairness.** ``tenant_keys.job_lock`` builds the Procrastinate lock string. Two jobs with the same
lock never run at once, so giving a tenant's jobs of one type ``max_per_tenant`` distinct slots
caps that tenant's concurrency for the type, while other tenants' jobs (other locks) are not
held up.
The key format is ``tenant:<id>:job:<type>:<slot>``.
"""

from __future__ import annotations

import datetime
import json
import os
from collections.abc import Iterable
from typing import Any

import procrastinate
from procrastinate import RetryStrategy
from procrastinate.jobs import Job
from procrastinate.retry import RetryDecision
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "DEFAULT_QUEUE",
    "JOBS_URL_ENV",
    "QUEUES",
    "JobRetryStrategy",
    "app",
    "defer_in_transaction",
    "jobs_conninfo",
    "run_worker",
]

JOBS_URL_ENV = "DATABASE_JOBS_URL"

# Queues are per job class, never per tenant (ADR 0003). Gotenberg and sandbox work run in
# their own worker processes (``--queues pdf``, ``--queues scan``).
QUEUES: tuple[str, ...] = ("default", "pdf", "scan", "import", "outbox")
DEFAULT_QUEUE = "default"

# Procrastinate's built-in tasks are not used and keep the defaults.
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(),
    worker_defaults={"shutdown_graceful_timeout": 60.0},
)


def jobs_conninfo() -> str:
    """The worker's libpq connection URL (``aip_jobs``), from ``DATABASE_JOBS_URL``."""
    url = os.environ.get(JOBS_URL_ENV, "")
    if not url:
        raise RuntimeError(f"{JOBS_URL_ENV} is not set")
    return url


class JobRetryStrategy(RetryStrategy):
    """Retry with exponential backoff; ``max_attempts`` counts the total number of tries.

    Procrastinate's ``RetryStrategy.max_attempts`` counts retries, so ``max_attempts=1`` would
    mean "retry once" (or forever when 0). Here ``max_attempts=1`` means one try and no retry.
    """

    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        # ``job.attempts`` is the number of earlier tries, so this try is number attempts + 1.
        if self.max_attempts is not None and job.attempts + 1 >= self.max_attempts:
            return None
        return super().get_retry_decision(exception=exception, job=job)

    def backoff_seconds(self, attempts: int) -> int:
        """Seconds to wait before the retry that follows try number ``attempts`` (1-based)."""
        return self.wait + self.linear_wait * (attempts - 1) + self.exponential_wait**attempts


_DEFER_SQL = text(
    """
    SELECT procrastinate_defer_jobs_v1(
        ARRAY[ROW(
            CAST(:queue_name AS character varying),
            CAST(:task_name AS character varying),
            CAST(:priority AS integer),
            CAST(:lock AS text),
            CAST(:queueing_lock AS text),
            CAST(:args AS jsonb),
            CAST(:scheduled_at AS timestamp with time zone)
        )]::procrastinate_job_to_defer_v1[]
    )
    """
)


async def defer_in_transaction(
    conn: AsyncConnection,
    *,
    task_name: str,
    queue: str,
    args: dict[str, Any],
    lock: str | None = None,
    priority: int = 0,
    scheduled_at: datetime.datetime | None = None,
) -> int:
    """Insert one Procrastinate job on ``conn`` and return its id; commits with ``conn``."""
    if queue not in QUEUES:
        raise ValueError(f"unknown queue {queue!r}; expected one of {', '.join(QUEUES)}")
    result = await conn.execute(
        _DEFER_SQL,
        {
            "queue_name": queue,
            "task_name": task_name,
            "priority": priority,
            "lock": lock,
            "queueing_lock": None,
            "args": json.dumps(args),
            "scheduled_at": scheduled_at,
        },
    )
    job_ids: list[int] = result.scalar_one()
    return job_ids[0]


async def run_worker(
    *,
    queues: Iterable[str],
    concurrency: int = 1,
    wait: bool = True,
    conninfo: str | None = None,
    install_signal_handlers: bool = True,
    **options: Any,
) -> None:
    """Run a worker for ``queues`` until stopped (SIGTERM finishes in-flight jobs first).

    ``wait=False`` returns once the queues are empty (tests, one-shot drains).
    """
    selected = list(queues)
    unknown = [q for q in selected if q not in QUEUES]
    if unknown:
        raise ValueError(f"unknown queue(s): {', '.join(unknown)}")
    connector = procrastinate.PsycopgConnector(conninfo=conninfo or jobs_conninfo())
    with app.replace_connector(connector):
        async with app.open_async():
            await app.run_worker_async(
                queues=selected,
                concurrency=concurrency,
                wait=wait,
                install_signal_handlers=install_signal_handlers,
                **options,
            )
