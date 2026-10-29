"""TESTING-13 (review 11 M10): the worker heartbeat and the container healthcheck that reads it."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from tests.fixtures.postgres import AUDIT_WRITER, JOBS, FreshDb

from aip.platform.db.engine import dispose_audit_writer_engine, dispose_jobs_engine
from aip.platform.jobs.heartbeat import beat_once, check, default_probes

# Generous: a slow laptop takes several seconds just to import the worker (TESTING-10).
WORKER_TIMEOUT = 90.0


def _healthcheck(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aip.platform.jobs.heartbeat", "--file", str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_fresh_beat_is_healthy_and_a_stale_or_missing_one_is_not(tmp_path: Path) -> None:
    beat = tmp_path / "beat"
    assert check(beat, 60) is not None and "no heartbeat" in str(check(beat, 60))
    beat.write_text("1000.0\n")
    assert check(beat, 60, now=1030.0) is None
    assert "stale heartbeat" in str(check(beat, 60, now=1100.0))
    beat.write_text("not a time\n")
    assert "unreadable" in str(check(beat, 60))


def test_the_healthcheck_command_exits_1_without_a_beat(tmp_path: Path) -> None:
    result = _healthcheck(tmp_path / "missing")
    assert result.returncode == 1
    assert "no heartbeat" in result.stderr


async def test_a_beat_needs_the_jobs_and_audit_writer_logins(
    migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    beat = tmp_path / "beat"
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS))
    monkeypatch.setenv("DATABASE_AUDIT_WRITER_URL", migrated_db.role_url(AUDIT_WRITER))
    try:
        assert await beat_once(beat, default_probes(audit_writer=True)) is True
        assert check(beat, 60) is None
    finally:
        await dispose_audit_writer_engine()

    # A wrong password (or host) for the audit writer: the beat is removed, not left to go stale.
    bad = migrated_db.role_url(AUDIT_WRITER).replace("aip_audit_writer_test_only", "wrong")
    monkeypatch.setenv("DATABASE_AUDIT_WRITER_URL", bad)
    try:
        assert await beat_once(beat, default_probes(audit_writer=True)) is False
        assert not beat.exists()
        # A worker that does not drain the outbox never needs the audit writer.
        assert await beat_once(beat, default_probes(audit_writer=False)) is True
    finally:
        await dispose_audit_writer_engine()
        await dispose_jobs_engine()


async def test_the_audit_writer_probe_refuses_a_privileged_login(
    migrated_db: FreshDb, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    beat = tmp_path / "beat"
    monkeypatch.setenv("DATABASE_JOBS_URL", migrated_db.role_url(JOBS))
    monkeypatch.setenv("DATABASE_AUDIT_WRITER_URL", migrated_db.owner_url)
    try:
        assert await beat_once(beat, default_probes(audit_writer=True)) is False
    finally:
        await dispose_audit_writer_engine()
        await dispose_jobs_engine()


def _start_worker(db: FreshDb, beat: Path, audit_writer_url: str) -> subprocess.Popen[str]:
    env = {
        **os.environ,
        "DATABASE_JOBS_URL": db.role_url(JOBS),
        "DATABASE_URL": db.app_url,
        "DATABASE_AUDIT_WRITER_URL": audit_writer_url,
        "WORKER_HEARTBEAT_FILE": str(beat),
        "WORKER_HEARTBEAT_INTERVAL_S": "1",
    }
    return subprocess.Popen(
        [sys.executable, "-m", "aip.worker", "--queues", "default,outbox"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop(proc: subprocess.Popen[str]) -> str:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
    return proc.stdout.read() if proc.stdout else ""


def _wait_registered(db: FreshDb, proc: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + WORKER_TIMEOUT
    while db.fetch("SELECT count(*) FROM procrastinate_workers") == [(0,)]:
        assert proc.poll() is None, _stop(proc)
        assert time.monotonic() < deadline, "worker did not register in time"
        time.sleep(0.25)


def test_a_running_worker_is_healthy_and_its_beat_goes_when_it_stops(
    migrated_db: FreshDb, tmp_path: Path
) -> None:
    beat = tmp_path / "beat"
    proc = _start_worker(migrated_db, beat, migrated_db.role_url(AUDIT_WRITER))
    try:
        _wait_registered(migrated_db, proc)
        deadline = time.monotonic() + WORKER_TIMEOUT
        while _healthcheck(beat).returncode != 0:
            assert proc.poll() is None, _stop(proc)
            assert time.monotonic() < deadline, "the worker never became healthy"
            time.sleep(0.5)
    finally:
        output = _stop(proc)
    assert proc.returncode == 0, output
    assert _healthcheck(beat).returncode == 1  # a stopped worker leaves no beat behind


def test_a_worker_with_a_bad_audit_writer_url_is_unhealthy(
    migrated_db: FreshDb, tmp_path: Path
) -> None:
    beat = tmp_path / "beat"
    bad = migrated_db.role_url(AUDIT_WRITER).replace("aip_audit_writer_test_only", "wrong")
    proc = _start_worker(migrated_db, beat, bad)
    try:
        _wait_registered(migrated_db, proc)
        # Several beat intervals: the worker keeps running, but never reports healthy.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            assert proc.poll() is None
            result = _healthcheck(beat)
            assert result.returncode == 1, "a worker without its audit writer reported healthy"
            time.sleep(0.5)
    finally:
        output = _stop(proc)
    assert "worker heartbeat failed" in output and "audit_writer" in output, output
