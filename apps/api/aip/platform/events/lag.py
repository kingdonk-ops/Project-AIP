"""Outbox lag smoke check (TESTING-13, review 11 M10).

    python -m aip.platform.events.lag [--max-lag 60] [--wait 120] [--max-dead-letters 0]

Connects as ``aip_jobs`` (``DATABASE_JOBS_URL``), the role that already reads every tenant's
``domain_events`` for the dispatcher, and reports the outbox: events waiting, the age of the oldest
one and dead letters. It exits 0 when no waiting event is older than ``--max-lag`` seconds and
there are at most ``--max-dead-letters`` dead letters. ``--wait`` re-checks every 2 s for up to that
many seconds before failing, so a stack that has just finished a test run gets time to drain.

A stopped worker, a dispatcher that never drains, or a subscriber that fails every delivery (say
the audit writer cannot log in) all fail the check. Run it inside the stack, for example
``docker compose exec worker python -m aip.platform.events.lag``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aip.platform.db.engine import dispose_jobs_engine, get_jobs_engine
from aip.platform.db.session import as_jobs_role

__all__ = ["OutboxLag", "lag_problems", "main", "outbox_lag"]

POLL_S = 2.0

_LAG = text("""
    SELECT
      count(*) FILTER (WHERE published_at IS NULL AND dead_lettered_at IS NULL
                         AND discarded_at IS NULL) AS waiting,
      coalesce(extract(epoch FROM now() - min(occurred_at) FILTER (
        WHERE published_at IS NULL AND dead_lettered_at IS NULL AND discarded_at IS NULL
      )), 0) AS oldest_s,
      count(*) FILTER (WHERE dead_lettered_at IS NOT NULL AND discarded_at IS NULL) AS dead,
      count(*) FILTER (WHERE published_at IS NOT NULL) AS published
    FROM domain_events
""")


@dataclass(frozen=True, slots=True)
class OutboxLag:
    waiting: int
    oldest_waiting_s: float
    dead_lettered: int
    published: int

    def summary(self) -> str:
        return (
            f"waiting={self.waiting} oldest_waiting_s={self.oldest_waiting_s:.1f} "
            f"dead_lettered={self.dead_lettered} published={self.published}"
        )


async def outbox_lag(jobs_engine: AsyncEngine) -> OutboxLag:
    async with as_jobs_role(jobs_engine) as conn:
        row = (await conn.execute(_LAG)).one()
    return OutboxLag(int(row.waiting), float(row.oldest_s), int(row.dead), int(row.published))


def lag_problems(lag: OutboxLag, *, max_lag_s: float, max_dead_letters: int) -> list[str]:
    """Why the outbox is unhealthy; empty when it is draining."""
    problems: list[str] = []
    if lag.waiting and lag.oldest_waiting_s > max_lag_s:
        problems.append(
            f"{lag.waiting} event(s) waiting, the oldest for {lag.oldest_waiting_s:.0f} s "
            f"(max {max_lag_s:.0f} s): is the worker running and draining the outbox?"
        )
    if lag.dead_lettered > max_dead_letters:
        problems.append(
            f"{lag.dead_lettered} dead-lettered event(s) (max {max_dead_letters}): "
            "a subscriber keeps failing (see last_error in domain_events)"
        )
    return problems


async def _check(max_lag_s: float, max_dead_letters: int, wait_s: float) -> int:
    deadline = time.monotonic() + wait_s
    try:
        while True:
            lag = await outbox_lag(get_jobs_engine())
            problems = lag_problems(lag, max_lag_s=max_lag_s, max_dead_letters=max_dead_letters)
            if not problems:
                print(f"OK outbox: {lag.summary()}")
                return 0
            if time.monotonic() >= deadline:
                print(f"FAIL outbox: {lag.summary()}", file=sys.stderr)
                for problem in problems:
                    print(f"FAIL {problem}", file=sys.stderr)
                return 1
            await asyncio.sleep(POLL_S)
    finally:
        await dispose_jobs_engine()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aip.platform.events.lag", description="Outbox lag smoke check."
    )
    parser.add_argument("--max-lag", type=float, default=60.0, help="seconds (default 60)")
    parser.add_argument("--max-dead-letters", type=int, default=0)
    parser.add_argument("--wait", type=float, default=0.0, help="seconds to wait for a drain")
    args = parser.parse_args(argv)
    return asyncio.run(_check(args.max_lag, args.max_dead_letters, args.wait))


if __name__ == "__main__":
    raise SystemExit(main())
