"""The worker heartbeat and its container healthcheck (TESTING-13, review 11 M10).

The worker runs :func:`run_heartbeat` next to Procrastinate. Every ``WORKER_HEARTBEAT_INTERVAL_S``
seconds (default 10) it checks that ``aip_jobs`` can log in and, when the worker drains the outbox,
that ``aip_audit_writer`` can too (the audit subscriber writes through it, AUDIT-02). On success it
writes the current time to ``WORKER_HEARTBEAT_FILE`` (default ``<tmp>/aip-worker-heartbeat``); on
failure it removes the file, so the check fails at once instead of when the beat goes stale.

The healthcheck reads that file::

    python -m aip.platform.jobs.heartbeat [--max-age 60]

and exits 0 only when the last beat is younger than ``--max-age`` seconds. A crash-looping worker,
a blocked event loop and a wrong ``DATABASE_AUDIT_WRITER_URL`` all make the container unhealthy.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

import structlog

__all__ = [
    "DEFAULT_HEARTBEAT_FILE",
    "HEARTBEAT_FILE_ENV",
    "HEARTBEAT_INTERVAL_ENV",
    "beat_once",
    "check",
    "heartbeat_file",
    "heartbeat_interval",
    "main",
    "run_heartbeat",
]

logger = structlog.stdlib.get_logger(__name__)

HEARTBEAT_FILE_ENV = "WORKER_HEARTBEAT_FILE"
HEARTBEAT_INTERVAL_ENV = "WORKER_HEARTBEAT_INTERVAL_S"
# The container's private tmpfs (/tmp, read_only root): tempfile honours TMPDIR elsewhere.
DEFAULT_HEARTBEAT_FILE = str(Path(tempfile.gettempdir()) / "aip-worker-heartbeat")
DEFAULT_INTERVAL_S = 10.0
DEFAULT_MAX_AGE_S = 60.0
# One probe may take this long before the beat counts as failed (a dead host never answers).
PROBE_TIMEOUT_S = 10.0

Probe = Callable[[], Awaitable[None]]


def heartbeat_file() -> Path:
    return Path(os.environ.get(HEARTBEAT_FILE_ENV) or DEFAULT_HEARTBEAT_FILE)


def heartbeat_interval() -> float:
    raw = os.environ.get(HEARTBEAT_INTERVAL_ENV)
    interval = float(raw) if raw else DEFAULT_INTERVAL_S
    if interval <= 0:
        raise ValueError(f"{HEARTBEAT_INTERVAL_ENV} must be positive")
    return interval


def default_probes(*, audit_writer: bool) -> list[tuple[str, Probe]]:
    """``aip_jobs`` always; ``aip_audit_writer`` when this worker drains the outbox."""
    from aip.platform.db.probes import probe_audit_writer, probe_jobs

    probes: list[tuple[str, Probe]] = [("jobs", probe_jobs)]
    if audit_writer:
        probes.append(("audit_writer", probe_audit_writer))
    return probes


async def beat_once(path: Path, probes: Sequence[tuple[str, Probe]]) -> bool:
    """Run every probe; write the beat when all pass, else remove it. True when healthy."""
    for name, probe in probes:
        try:
            await asyncio.wait_for(probe(), timeout=PROBE_TIMEOUT_S)
        except Exception as exc:
            path.unlink(missing_ok=True)
            logger.warning(
                "worker heartbeat failed", probe=name, error=f"{type(exc).__name__}: {exc}"
            )
            return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"{time.time():.3f}\n", encoding="ascii")
    tmp.replace(path)  # atomic: the check never reads a half-written beat
    return True


async def run_heartbeat(path: Path, probes: Sequence[tuple[str, Probe]], interval_s: float) -> None:
    """Beat every ``interval_s`` seconds until cancelled; the file is removed on the way out."""
    healthy: bool | None = None
    try:
        while True:
            ok = await beat_once(path, probes)
            if ok and healthy is not True:
                logger.info("worker heartbeat healthy", file=str(path))
            healthy = ok
            await asyncio.sleep(interval_s)
    finally:
        path.unlink(missing_ok=True)


def check(path: Path, max_age_s: float, now: float | None = None) -> str | None:
    """Why the worker is unhealthy, or ``None`` when its last beat is fresh."""
    try:
        beat = float(path.read_text(encoding="ascii").strip())
    except FileNotFoundError:
        return f"no heartbeat at {path}: the worker is starting, stopped or failing its probes"
    except (OSError, ValueError) as exc:
        return f"unreadable heartbeat at {path}: {exc}"
    age = (time.time() if now is None else now) - beat
    if age > max_age_s:
        return f"stale heartbeat: last beat {age:.0f} s ago (max {max_age_s:.0f} s)"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aip.platform.jobs.heartbeat",
        description="Exit 0 when the worker's heartbeat is fresh (container healthcheck).",
    )
    parser.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE_S, help="seconds")
    parser.add_argument("--file", type=Path, default=None, help=f"default: ${HEARTBEAT_FILE_ENV}")
    args = parser.parse_args(argv)
    problem = check(args.file or heartbeat_file(), args.max_age)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
