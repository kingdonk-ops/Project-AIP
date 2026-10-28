"""TESTING-13 (review 11 M10): the worker's heartbeat and the ``aip.worker_health`` healthcheck.

A worker is healthy only while it keeps reaching its databases: ``aip_jobs`` always, and
``aip_audit_writer`` when it works the ``outbox`` queue. Real Postgres; the bad audit-writer URL is
the real login with a wrong password.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from tests.fixtures.postgres import AUDIT_WRITER, JOBS, ROLE_PASSWORDS, FreshDb

from aip import worker_health
from aip.platform.db.engine import dispose_audit_writer_engine, dispose_jobs_engine
from aip.worker import heartbeat_once

WORKER_STARTUP_TIMEOUT = 60.0  # a slow laptop takes several seconds to import the worker


def bad_audit_writer_url(db: FreshDb) -> str:
    good = db.role_url(AUDIT_WRITER)
    password = ROLE_PASSWORDS[AUDIT_WRITER]
    assert password in good
    return good.replace(password, "not_the_audit_writer_password")


def healthcheck(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """``python -m aip.worker_health``: the exact command the compose healthcheck runs."""
    return subprocess.run(
        [sys.executable, "-m", "aip.worker_health", *extra],
        env={**os.environ, worker_health.HEARTBEAT_FILE_ENV: str(path)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


# --- the check -----------------------------------------------------------------------------------


def test_no_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    problem = worker_health.check(tmp_path / "beat")
    assert problem is not None and "no heartbeat" in problem


def test_a_fresh_heartbeat_is_healthy_and_a_stale_one_is_not(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    worker_health.write_heartbeat(path, now=1000.0)
    assert worker_health.check(path, 60, clock=lambda: 1059.0) is None
    stale = worker_health.check(path, 60, clock=lambda: 1061.0)
    assert stale is not None and "61 s old" in stale


def test_garbage_in_the_heartbeat_is_unhealthy(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    path.write_text("not a time", encoding="ascii")
    assert worker_health.check(path) is not None


def test_the_command_exits_1_without_a_heartbeat_and_0_with_one(tmp_path: Path) -> None:
    path = tmp_path / "beat"
    missing = healthcheck(path)
    assert missing.returncode == 1
    assert "worker unhealthy" in missing.stderr
    worker_health.write_heartbeat(path)
    assert healthcheck(path).returncode == 0


def test_the_heartbeat_file_defaults_to_tmp() -> None:
    assert worker_health.heartbeat_path({}) == Path("/tmp/aip-worker-heartbeat")
    assert worker_health.heartbeat_path({"WORKER_HEARTBEAT_FILE": "/x/y"}) == Path("/x/y")


# --- one probe against Postgres ------------------------------------------------------------------


@pytest.fixture
async def engines() -> AsyncIterator[None]:
    await dispose_jobs_engine()
    await dispose_audit_writer_engine()
    yield
    await dispose_jobs_engine()
    await dispose_audit_writer_engine()


@pytest.mark.usefixtures("engines")
async def test_reaching_both_databases_writes_the_heartbeat(
    migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS))
    monkeypatch.setenv("DATABASE_AUDIT_WRITER_URL", migrated_db.role_url(AUDIT_WRITER))
    path = tmp_path / "beat"
    assert await heartbeat_once(path, audit_writer=True) is True
    assert worker_health.check(path) is None
    assert healthcheck(path).returncode == 0


@pytest.mark.usefixtures("engines")
async def test_a_bad_audit_writer_url_makes_the_healthcheck_fail(
    migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS))
    monkeypatch.setenv("DATABASE_AUDIT_WRITER_URL", bad_audit_writer_url(migrated_db))
    path = tmp_path / "beat"
    worker_health.write_heartbeat(path)  # healthy a moment ago
    assert await heartbeat_once(path, audit_writer=True) is False
    assert not path.exists()
    result = healthcheck(path)
    assert result.returncode == 1, result.stdout + result.stderr


@pytest.mark.usefixtures("engines")
async def test_an_unset_audit_writer_url_is_unhealthy_for_the_outbox_worker(
    migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS))
    monkeypatch.delenv("DATABASE_AUDIT_WRITER_URL", raising=False)
    path = tmp_path / "beat"
    assert await heartbeat_once(path, audit_writer=True) is False
    # A worker of other queues (scan, pdf) never writes the chains and does not need the login.
    assert await heartbeat_once(path, audit_writer=False) is True


@pytest.mark.usefixtures("engines")
async def test_a_bad_jobs_url_is_unhealthy(
    migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS).replace("aip_jobs", "nope"))
    path = tmp_path / "beat"
    assert await heartbeat_once(path, audit_writer=False) is False


# --- the running worker --------------------------------------------------------------------------


def _start_worker(db: FreshDb, audit_writer_url: str, path: Path) -> subprocess.Popen[str]:
    env = {
        **os.environ,
        "DATABASE_JOBS_URL": db.role_url(JOBS),
        "DATABASE_URL": db.app_url,
        "DATABASE_AUDIT_WRITER_URL": audit_writer_url,
        worker_health.HEARTBEAT_FILE_ENV: str(path),
        worker_health.HEARTBEAT_INTERVAL_ENV: "1",
    }
    return subprocess.Popen(
        [sys.executable, "-m", "aip.worker", "--queues", "default,outbox", "--concurrency", "1"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_registered(db: FreshDb, proc: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + WORKER_STARTUP_TIMEOUT
    while db.fetch("SELECT count(*) FROM procrastinate_workers") != [(1,)]:
        assert proc.poll() is None, proc.stdout.read() if proc.stdout else ""
        assert time.monotonic() < deadline, "worker did not register in time"
        time.sleep(0.25)


def _stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_a_running_worker_is_healthy_and_clears_its_heartbeat_on_exit(
    migrated_db: FreshDb, tmp_path: Path
) -> None:
    path = tmp_path / "beat"
    proc = _start_worker(migrated_db, migrated_db.role_url(AUDIT_WRITER), path)
    try:
        _wait_registered(migrated_db, proc)
        deadline = time.monotonic() + 30
        while healthcheck(path).returncode != 0:
            assert proc.poll() is None, proc.stdout.read() if proc.stdout else ""
            assert time.monotonic() < deadline, "the worker never became healthy"
            time.sleep(0.5)
    finally:
        _stop(proc)
    assert not path.exists()


def test_a_running_worker_with_a_bad_audit_writer_url_stays_unhealthy(
    migrated_db: FreshDb, tmp_path: Path
) -> None:
    path = tmp_path / "beat"
    proc = _start_worker(migrated_db, bad_audit_writer_url(migrated_db), path)
    try:
        _wait_registered(migrated_db, proc)
        # Several 1-second heartbeat rounds: the jobs login works, the audit writer's never does.
        for _ in range(6):
            result = healthcheck(path)
            assert result.returncode == 1, "a worker that cannot reach the audit writer is healthy"
            time.sleep(0.5)
        assert proc.poll() is None  # unhealthy, not crashed: the orchestrator restarts it
    finally:
        _stop(proc)
