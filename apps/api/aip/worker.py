"""Job worker entrypoint (OPS-02, ADR 0003).

::

    uv run python -m aip.worker --queues default,outbox [--concurrency 4]

Imports every enabled module's ``jobs.py`` (where handlers call ``ops.register``) and the
platform's own periodic jobs (``PLATFORM_JOB_MODULES``), then runs the Procrastinate worker for
the given queues. It connects as ``aip_jobs`` (``DATABASE_JOBS_URL``) and each job runs inside
``with_tenant(payload.tenant_id)``. SIGTERM/SIGINT stop it gracefully: no new job is fetched and
in-flight jobs finish (up to ``--shutdown-timeout`` seconds, then they are aborted and recovered
later as stalled). Peak memory above 95% of ``WORKER_MEMORY_LIMIT_MB`` also
triggers that graceful stop, so the orchestrator restarts the process.

Gotenberg (``pdf``) and sandbox (``scan``) work run in their own worker processes: start one
process per queue group.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import os
import signal
import sys
from collections.abc import Sequence

from aip.modules.ops.runner import memory_guard
from aip.modules.terms.api import install as install_term_resolver
from aip.platform.db.engine import dispose_engine, dispose_jobs_engine, get_jobs_engine
from aip.platform.db.tls import check_transport_security
from aip.platform.dev_secrets import check_no_dev_secrets
from aip.platform.events.jobs import active_subscribers
from aip.platform.jobs.app import DEFAULT_QUEUE, QUEUES, run_worker
from aip.platform.modules.registry import (
    DEFAULT_MODULES_PACKAGE,
    MODULES_PACKAGE_ENV,
    load_modules,
)
from aip.platform.observability.logging import configure_logging

__all__ = ["PLATFORM_JOB_MODULES", "check_jobs_login", "import_job_modules", "main", "parse_args"]

logger = logging.getLogger(__name__)

# Platform jobs that belong to no module: the daily partition maintenance (DATABASE-05) and
# the outbox dispatcher (ARCH-07).
PLATFORM_JOB_MODULES: tuple[str, ...] = (
    "aip.platform.db.jobs",
    "aip.platform.events.jobs",
)


def import_job_modules(package: str | None = None) -> list[str]:
    """Import ``jobs.py`` of every enabled module; returns the module names imported.

    ``package`` defaults to ``AIP_MODULES_PACKAGE`` or ``aip.modules``; ``AIP_DISABLED_MODULES``
    applies, exactly as for the API.
    """
    package = package or os.environ.get(MODULES_PACKAGE_ENV) or DEFAULT_MODULES_PACKAGE
    imported: list[str] = []
    for module in load_modules(package):
        name = f"{package}.{module.id}.jobs"
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:  # a missing import inside jobs.py is a real error
                raise
            continue
        imported.append(name)
    return imported


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m aip.worker", description=__doc__)
    parser.add_argument(
        "--queues",
        default=DEFAULT_QUEUE,
        help=f"comma-separated queues to work ({', '.join(QUEUES)}); default: {DEFAULT_QUEUE}",
    )
    parser.add_argument("--concurrency", type=int, default=4, help="jobs run in parallel")
    parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=60.0,
        help="seconds in-flight jobs may take to finish after SIGTERM",
    )
    args = parser.parse_args(argv)
    args.queue_list = [q.strip() for q in str(args.queues).split(",") if q.strip()]
    unknown = [q for q in args.queue_list if q not in QUEUES]
    if not args.queue_list or unknown:
        parser.error(f"--queues must be a comma-separated subset of: {', '.join(QUEUES)}")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    return args


async def check_jobs_login() -> None:
    """Open one ``aip_jobs`` connection now, so a privileged login stops startup.

    The engine refuses an owner, superuser, BYPASSRLS or CREATEROLE login on connect
    (``DatabaseConfigError``); finding out here beats failing every job later.
    """
    async with get_jobs_engine().connect():
        pass


async def _run(queues: list[str], concurrency: int, shutdown_timeout: float) -> None:
    try:
        await check_jobs_login()
        await run_worker(
            queues=queues,
            concurrency=concurrency,
            shutdown_graceful_timeout=shutdown_timeout,
        )
    finally:
        await dispose_jobs_engine()
        await dispose_engine()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()
    check_transport_security()  # STACK-07: production needs verified TLS to Postgres and Redis
    check_no_dev_secrets()  # SECURITY-11: public dev secrets only in development and test
    for name in PLATFORM_JOB_MODULES:
        importlib.import_module(name)
    imported = import_job_modules()
    active_subscribers()  # ARCH-07: a subscriber missing from its manifest stops boot
    install_term_resolver()  # TERMS-02: the aip.platform.terms port for emails and PDFs
    logger.info("job modules loaded: %s", ", ".join(imported) or "none")
    # Procrastinate's signal handler turns SIGTERM into a graceful stop.
    memory_guard.on_exceeded = lambda: signal.raise_signal(signal.SIGTERM)
    asyncio.run(_run(args.queue_list, args.concurrency, args.shutdown_timeout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
