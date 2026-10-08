"""OPS-02: the worker entrypoint ``python -m aip.worker``."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest
from tests.platform.db.conftest import JOBS, FreshDb

from aip.worker import import_job_modules, parse_args


def test_queues_default_to_the_default_queue() -> None:
    args = parse_args([])
    assert args.queue_list == ["default"]


def test_queues_are_a_comma_separated_subset_of_the_job_classes() -> None:
    assert parse_args(["--queues", "default,outbox"]).queue_list == ["default", "outbox"]
    assert parse_args(["--queues", "pdf", "--concurrency", "2"]).concurrency == 2


@pytest.mark.parametrize("bad", ["tenant-a", "default,nope", ",", ""])
def test_unknown_queues_are_refused(bad: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--queues", bad])
    assert "--queues" in capsys.readouterr().err


def test_zero_concurrency_is_refused() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--concurrency", "0"])


def test_every_enabled_modules_jobs_py_is_imported() -> None:
    assert "aip.modules.identity.jobs" in import_job_modules()


def test_a_sigterm_stops_an_idle_worker_gracefully(migrated_db: FreshDb) -> None:
    env = {
        **os.environ,
        "DATABASE_JOBS_URL": migrated_db.role_url(JOBS),
        "DATABASE_URL": migrated_db.app_url,
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "aip.worker", "--queues", "default,outbox", "--concurrency", "2"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        time.sleep(4)  # connect, register the worker, start polling
        assert proc.poll() is None, proc.stdout.read() if proc.stdout else ""
        assert migrated_db.fetch("SELECT count(*) FROM procrastinate_workers") == [(1,)]
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    # A graceful stop unregisters the worker.
    assert migrated_db.fetch("SELECT count(*) FROM procrastinate_workers") == [(0,)]
