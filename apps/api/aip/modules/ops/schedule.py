"""The scheduled-job trigger (OPS-13): one command that enqueues a named, registered job.

  python -m aip.modules.ops.schedule enqueue <job> --tenant <id> [--tenant <id> ...]
  python -m aip.modules.ops.schedule enqueue <job> --all-tenants [--period 2026-10]
  python -m aip.modules.ops.schedule check

The trigger holds no business logic: a Coolify scheduled task now, EventBridge Scheduler running the
API image as an ECS task in AWS (docs/runbooks/scheduled-jobs.md). The job itself is an ordinary
registered Procrastinate job.

- The job must be registered (every module's ``jobs.py`` is imported first); an unknown name
  exits 2.
- Each enqueue carries the idempotency key ``schedule:<job>:<period>``, so a trigger that fires
  twice in one period enqueues once per tenant. The period comes from the job's
  ``[[schedules]]`` entry in its module manifest (``month`` by default), or ``--period``.
- ``--all-tenants`` lists active tenants through ``ops_active_tenant_ids()`` (ADR 0032) and enqueues
  in each tenant's own ``with_tenant`` transaction as ``aip_app``, exactly as a request would.
- ``check`` fails (exit 1) when a manifest schedule names a job that is not registered.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from aip.platform.context import RequestContext, new_request_id, use_context
from aip.platform.db.engine import dispose_engine
from aip.platform.db.session import before_tenant, with_tenant
from aip.platform.modules.manifest import ModuleManifest, ScheduleEntry

from .enqueue import enqueue
from .registry import registered_types
from .schemas import JobView

__all__ = [
    "check_schedules",
    "enqueue_scheduled",
    "idempotency_key",
    "main",
    "period_key",
    "schedules",
]

Period = str
_MODULES_DIR = Path(__file__).resolve().parents[1]


def period_key(period: str, now: datetime.datetime) -> str:
    """The idempotency window ``now`` falls in: ``2026-10`` (month), ``2026-W42`` (week), ..."""
    now = now.astimezone(datetime.UTC)
    if period == "month":
        return now.strftime("%Y-%m")
    if period == "week":
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"
    if period == "day":
        return now.strftime("%Y-%m-%d")
    if period == "hour":
        return now.strftime("%Y-%m-%dT%H")
    raise ValueError(f"unknown period {period!r}")


def idempotency_key(job: str, period: str) -> str:
    return f"schedule:{job}:{period}"


def schedules(manifests: Iterable[ModuleManifest]) -> dict[str, ScheduleEntry]:
    """Every declared schedule, by job name."""
    return {entry.job: entry for manifest in manifests for entry in manifest.schedules}


def check_schedules(manifests: Iterable[ModuleManifest], registered: Iterable[str]) -> list[str]:
    """Problems: a schedule naming an unregistered job (empty when all is well)."""
    known = set(registered)
    return [
        f"{manifest.id}: schedule names job {entry.job!r}, which is not registered"
        for manifest in manifests
        for entry in manifest.schedules
        if entry.job not in known
    ]


def _load() -> tuple[list[ModuleManifest], frozenset[str]]:
    """Import every module's jobs (as the worker does) and read the manifests."""
    from aip.worker import import_job_modules  # the worker's own loader: same jobs, same order

    import_job_modules()
    manifests = [
        ModuleManifest.from_toml(path)
        for path in sorted(_MODULES_DIR.glob("*/manifest.toml"))
        if not path.parent.name.startswith(("_", "."))
    ]
    return manifests, registered_types()


async def active_tenants() -> list[UUID]:
    async with before_tenant() as conn:
        rows = (await conn.execute(text("SELECT ops_active_tenant_ids()"))).scalars().all()
    return [UUID(str(r)) for r in rows]


async def enqueue_scheduled(
    job: str, tenants: Sequence[UUID], period: Period
) -> list[tuple[UUID, JobView]]:
    """Enqueue ``job`` once per tenant for ``period`` (a repeat in the same period is a no-op)."""
    out: list[tuple[UUID, JobView]] = []
    for tenant in tenants:
        ctx = RequestContext(tenant_id=tenant, request_id=new_request_id())
        with use_context(ctx):
            async with with_tenant(ctx) as conn:
                view = await enqueue(
                    conn, job, {"period": period}, idempotency_key=idempotency_key(job, period)
                )
        out.append((tenant, view))
    return out


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m aip.modules.ops.schedule", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("enqueue", help="enqueue a registered job")
    run.add_argument("job")
    who = run.add_mutually_exclusive_group(required=True)
    who.add_argument("--tenant", action="append", type=UUID, default=None)
    who.add_argument("--all-tenants", action="store_true")
    run.add_argument("--period", help="the idempotency window, e.g. 2026-10 (default: now)")
    sub.add_parser("check", help="every manifest schedule names a registered job")
    return parser


async def _enqueue(args: argparse.Namespace, manifests: list[ModuleManifest]) -> int:
    try:
        tenants = await active_tenants() if args.all_tenants else list(args.tenant)
        entry = schedules(manifests).get(args.job)
        period = args.period or period_key(
            entry.period if entry else "month", datetime.datetime.now(datetime.UTC)
        )
        for tenant, view in await enqueue_scheduled(args.job, tenants, period):
            print(f"{tenant}: {args.job} {period} -> job {view.id} ({view.status.value})")
        print(f"{len(tenants)} tenant(s)")
        return 0
    finally:
        await dispose_engine()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifests, registered = _load()
    if args.command == "check":
        problems = check_schedules(manifests, registered)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    if args.job not in registered:
        print(
            f"unknown job {args.job!r}; registered: {', '.join(sorted(registered))}",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_enqueue(args, manifests))


if __name__ == "__main__":
    raise SystemExit(main())
