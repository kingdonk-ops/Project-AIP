"""Tests for tools/new_module.py (ARCH-01)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "new_module.py"


def run_scaffolder(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / "tools" / "new_module.py"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def repo_copy(tmp_path: Path) -> Path:
    """A minimal temp copy of the repo (scaffolder + api package) under git."""
    repo = tmp_path / "repo"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache")
    shutil.copytree(ROOT / "tools", repo / "tools", ignore=ignore)
    shutil.copytree(ROOT / "apps" / "api", repo / "apps" / "api", ignore=ignore)
    shutil.copy(ROOT / "pyproject.toml", repo / "pyproject.toml")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        "init",
    )
    return repo


def child_env(repo: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo / "apps" / "api"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return env


# --- unit -----------------------------------------------------------------


@pytest.mark.parametrize("name", ["Bad Name", "widgets-x", "Widgets", "1widgets", "", "_x"])
def test_rejects_invalid_names(name: str) -> None:
    result = run_scaffolder(ROOT, name)
    assert result.returncode != 0
    assert "invalid module name" in result.stderr


def test_requires_exactly_one_argument() -> None:
    result = run_scaffolder(ROOT)
    assert result.returncode != 0


# --- integration ----------------------------------------------------------


def test_generates_module_whose_smoke_test_passes(repo_copy: Path) -> None:
    result = run_scaffolder(repo_copy, "widgets")
    assert result.returncode == 0, result.stderr

    module = repo_copy / "apps" / "api" / "aip" / "modules" / "widgets"
    expected = {
        "__init__.py",
        "api.py",
        "tables.py",
        "schemas.py",
        "repository.py",
        "service.py",
        "policies.py",
        "events.py",
        "routes.py",
        "jobs.py",
        "manifest.toml",
        "tests",
    }
    assert expected <= {p.name for p in module.iterdir()}
    for path in module.rglob("*"):
        if path.is_file():
            assert "__module__" not in path.read_text(), path
    assert 'id = "widgets"' in (module / "manifest.toml").read_text()
    # no leftover staging folders
    assert not [p for p in module.parent.iterdir() if p.name.startswith(".")]

    tests = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "apps/api/aip/modules/widgets",
        ],
        cwd=repo_copy,
        env=child_env(repo_copy),
        capture_output=True,
        text=True,
        check=False,
    )
    assert tests.returncode == 0, tests.stdout + tests.stderr
    assert "1 passed" in tests.stdout


def test_refuses_existing_module_and_changes_nothing(repo_copy: Path) -> None:
    assert run_scaffolder(repo_copy, "widgets").returncode == 0
    before = git(repo_copy, "status", "--porcelain", "--untracked-files=all")

    second = run_scaffolder(repo_copy, "widgets")
    assert second.returncode == 1
    assert "module widgets already exists" in second.stderr
    assert git(repo_copy, "status", "--porcelain", "--untracked-files=all") == before


def test_refuses_to_overwrite_template(repo_copy: Path) -> None:
    result = run_scaffolder(repo_copy, "_template")
    assert result.returncode != 0
    assert git(repo_copy, "status", "--porcelain") == ""


# --- e2e ------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_uvicorn_serves_health_with_generated_module(repo_copy: Path) -> None:
    assert run_scaffolder(repo_copy, "widgets").returncode == 0
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "aip.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=repo_copy / "apps" / "api",
        env=child_env(repo_copy),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                response = httpx.get(
                    f"http://127.0.0.1:{port}/api/v1/health", timeout=1, trust_env=False
                )
                break
            except httpx.TransportError:
                if time.monotonic() > deadline or proc.poll() is not None:
                    raise
                time.sleep(0.2)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# --- layout (ADR 0004) ----------------------------------------------------


def test_no_forbidden_top_level_paths() -> None:
    for forbidden in ("backend", "frontend", "services"):
        assert not (ROOT / forbidden).exists(), forbidden


def test_no_typescript_under_api() -> None:
    api = ROOT / "apps" / "api"
    offenders = [
        p for p in api.rglob("*") if p.suffix in {".ts", ".tsx"} and ".venv" not in p.parts
    ]
    assert offenders == []
