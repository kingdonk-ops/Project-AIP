"""Integration tests for the generated API client drift check (STACK-03).

They run ``tools/ci/check_client_drift.sh`` in a temp git copy of the repo, so they never touch the
real tree. They need pnpm and installed node_modules; without them they skip (the CI
``api-client`` job installs both and runs this file).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLIENT = Path("packages") / "api-client"

pytestmark = pytest.mark.skipif(
    shutil.which("pnpm") is None or not (ROOT / CLIENT / "node_modules").is_dir(),
    reason="needs pnpm and installed node_modules (pnpm install)",
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture(scope="module")
def repo_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Tracked + untracked (not ignored) files copied into a fresh git repo, node_modules linked."""
    repo = tmp_path_factory.mktemp("drift") / "repo"
    listed = git(ROOT, "ls-files", "-co", "--exclude-standard", "-z").split("\0")
    for rel in filter(None, listed):
        src = ROOT / rel
        if not src.is_file():
            continue  # deleted in the working tree
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in (Path("node_modules"), CLIENT / "node_modules"):
        (repo / rel).symlink_to(ROOT / rel, target_is_directory=True)
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.name=test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "snapshot",
    )
    return repo


def run_drift(repo: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "AIP_PYTHON": sys.executable}
    return subprocess.run(
        ["bash", "tools/ci/check_client_drift.sh"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_tree_has_no_drift(repo_copy: Path) -> None:
    result = run_drift(repo_copy)
    assert result.returncode == 0, result.stdout + result.stderr


def test_changed_response_model_without_regenerating_fails(repo_copy: Path) -> None:
    main = repo_copy / "apps" / "api" / "aip" / "main.py"
    source = main.read_text(encoding="utf-8")
    marker = "class HealthResponse(BaseModel):\n"
    assert marker in source
    head, _, tail = source.partition(marker)
    main.write_text(head + marker + "    uptime_s: int\n" + tail, encoding="utf-8")
    try:
        result = run_drift(repo_copy)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "uptime_s" in result.stdout
    finally:
        git(repo_copy, "checkout", "--", ".")
