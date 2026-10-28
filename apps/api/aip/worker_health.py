"""The worker's container healthcheck (TESTING-13, review 11 M10). Standard library only.

::

    python -m aip.worker_health [--max-age 60]

Exit 0 when the heartbeat file is younger than ``--max-age`` seconds, else 1 with one line on
stderr. ``python -m aip.worker`` rewrites the file every ``WORKER_HEARTBEAT_INTERVAL_S`` seconds
(default 10), but only after it has just reached every database it needs: ``aip_jobs``
(``DATABASE_JOBS_URL``) always, and ``aip_audit_writer`` (``DATABASE_AUDIT_WRITER_URL``) when it
works the ``outbox`` queue, whose catch-all audit subscriber writes the chains (AUDIT-02). A probe
that fails deletes the file at once. So a worker that crash-loops, hangs, or cannot reach the
audit writer is unhealthy, which ``python -c "import aip"`` never was.

The file is ``$WORKER_HEARTBEAT_FILE``, default ``/tmp/aip-worker-heartbeat`` (the containers'
root filesystem is read-only; ``/tmp`` is a tmpfs). It holds the Unix time of the last good probe.
This module imports nothing from the app, so the check stays cheap on a busy container.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

__all__ = [
    "DEFAULT_HEARTBEAT_FILE",
    "DEFAULT_INTERVAL_S",
    "DEFAULT_MAX_AGE_S",
    "HEARTBEAT_FILE_ENV",
    "HEARTBEAT_INTERVAL_ENV",
    "check",
    "clear_heartbeat",
    "heartbeat_path",
    "main",
    "write_heartbeat",
]

HEARTBEAT_FILE_ENV = "WORKER_HEARTBEAT_FILE"
HEARTBEAT_INTERVAL_ENV = "WORKER_HEARTBEAT_INTERVAL_S"
DEFAULT_HEARTBEAT_FILE = "/tmp/aip-worker-heartbeat"
DEFAULT_INTERVAL_S = 10.0
DEFAULT_MAX_AGE_S = 60.0


def heartbeat_path(environ: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env.get(HEARTBEAT_FILE_ENV) or DEFAULT_HEARTBEAT_FILE)


def write_heartbeat(path: Path, now: float | None = None) -> None:
    """Record a good probe: write the time to a sibling file, then rename it over ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(f"{time.time() if now is None else now:.3f}\n", encoding="ascii")
    tmp.replace(path)


def clear_heartbeat(path: Path) -> None:
    """A failed probe or a stopping worker: the next healthcheck fails at once."""
    path.unlink(missing_ok=True)


def check(
    path: Path, max_age_s: float = DEFAULT_MAX_AGE_S, clock: Callable[[], float] = time.time
) -> str | None:
    """``None`` when the heartbeat is fresh, else why the worker is unhealthy."""
    try:
        raw = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return f"no heartbeat at {path}: the worker is starting, stopped or cannot reach a database"
    except OSError as exc:
        return f"cannot read the heartbeat {path}: {exc}"
    try:
        beat = float(raw)
    except ValueError:
        return f"the heartbeat {path} is not a timestamp"
    age = clock() - beat
    if age > max_age_s:
        return f"the last heartbeat is {age:.0f} s old (limit {max_age_s:.0f} s)"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m aip.worker_health", description=__doc__)
    parser.add_argument(
        "--max-age",
        type=float,
        default=DEFAULT_MAX_AGE_S,
        help=f"seconds a heartbeat stays fresh (default {DEFAULT_MAX_AGE_S:.0f})",
    )
    args = parser.parse_args(argv)
    problem = check(heartbeat_path(), args.max_age)
    if problem is not None:
        print(f"worker unhealthy: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
