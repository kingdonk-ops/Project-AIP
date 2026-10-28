"""Outbox lag smoke check (TESTING-13, review 11 M10).

::

    python -m aip.platform.events.lag [--max-age 60] [--wait 0]

Reads ``domain_events`` across tenants as ``aip_jobs`` (``DATABASE_JOBS_URL``; the dispatcher's
own ``dispatcher_select`` policy) and fails when the outbox is not draining:

- an event that is neither published nor discarded is older than ``--max-age`` seconds (the
  dispatcher is not running, or a subscriber keeps failing and the event waits in backoff); or
- an event is dead-lettered and not yet discarded by an operator (ADR 0030).

With ``--wait N`` it re-checks every second for up to ``N`` seconds before failing, so a check run
right after a burst of writes gives the dispatcher (every 2 s) time to catch up. Exit 0 when the
outbox is healthy, else 1 with one line per problem. CI runs it inside the compose ``worker``
container after the skeleton journeys; it works on any deployment where you can run a command in
the worker's image. It reports counts and ages only, never an event's payload.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import text

from aip.platform.db.engine import dispose_jobs_engine, get_jobs_engine
from aip.platform.db.session import DbEngine as AsyncEngine

__all__ = ["DEFAULT_MAX_AGE_S", "OutboxLag", "check", "main", "measure", "problems"]

DEFAULT_MAX_AGE_S = 60.0

_LAG = text("""
    SELECT count(*) FILTER (WHERE dead_lettered_at IS NULL) AS pending,
           count(*) FILTER (WHERE dead_lettered_at IS NOT NULL) AS dead_lettered,
           EXTRACT(EPOCH FROM now() - min(occurred_at) FILTER (WHERE dead_lettered_at IS NULL))
             AS oldest_pending_s
      FROM domain_events
     WHERE published_at IS NULL AND discarded_at IS NULL
""")


@dataclass(frozen=True, slots=True)
class OutboxLag:
    """Unpublished, undiscarded events: live ones (and the oldest's age) and dead-lettered ones."""

    pending: int
    dead_lettered: int
    oldest_pending_s: float | None


async def measure(engine: AsyncEngine) -> OutboxLag:
    async with engine.connect() as conn:
        row = (await conn.execute(_LAG)).one()
    oldest = None if row.oldest_pending_s is None else float(row.oldest_pending_s)
    return OutboxLag(int(row.pending), int(row.dead_lettered), oldest)


def problems(lag: OutboxLag, max_age_s: float) -> list[str]:
    found: list[str] = []
    if lag.oldest_pending_s is not None and lag.oldest_pending_s > max_age_s:
        found.append(
            f"outbox lag: {lag.pending} event(s) unpublished, the oldest for"
            f" {lag.oldest_pending_s:.0f} s (limit {max_age_s:.0f} s)"
        )
    if lag.dead_lettered:
        found.append(f"outbox: {lag.dead_lettered} dead-lettered event(s) not discarded")
    return found


async def check(
    engine: AsyncEngine,
    max_age_s: float = DEFAULT_MAX_AGE_S,
    wait_s: float = 0.0,
    *,
    clock: Callable[[], float] = time.monotonic,
    poll_s: float = 1.0,
) -> tuple[OutboxLag, list[str]]:
    """The lag and its problems; with ``wait_s`` re-measured until healthy or out of time."""
    deadline = clock() + wait_s
    while True:
        lag = await measure(engine)
        found = problems(lag, max_age_s)
        if not found or clock() >= deadline:
            return lag, found
        await asyncio.sleep(poll_s)


async def _run(max_age_s: float, wait_s: float) -> tuple[OutboxLag, list[str]]:
    try:
        return await check(get_jobs_engine(), max_age_s, wait_s)
    finally:
        await dispose_jobs_engine()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aip.platform.events.lag", description=__doc__)
    parser.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE_S)
    parser.add_argument("--wait", type=float, default=0.0)
    args = parser.parse_args(argv)
    lag, found = asyncio.run(_run(args.max_age, args.wait))
    for problem in found:
        print(f"FAIL {problem}", file=sys.stderr)
    if found:
        return 1
    oldest = "none" if lag.oldest_pending_s is None else f"{lag.oldest_pending_s:.0f} s"
    print(f"OK outbox: {lag.pending} event(s) in flight, oldest {oldest}, none dead-lettered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
