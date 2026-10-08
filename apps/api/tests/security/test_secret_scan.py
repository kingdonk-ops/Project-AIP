"""Secret scanning gate (SECURITY-08): a planted secret makes gitleaks exit non-zero.

Runs with the gitleaks binary when it is on PATH, otherwise with the image named in
AIP_TEST_GITLEAKS_IMAGE (security.yml sets it to the pinned image). Skipped when neither is there.
The fake AWS key is generated at run time, so no key-shaped string is ever committed.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def _gitleaks_dir(directory: Path) -> subprocess.CompletedProcess[str]:
    binary = shutil.which("gitleaks")
    if binary is not None:
        argv = [binary, "dir", "--no-banner", "--redact", str(directory)]
    else:
        image = os.environ.get("AIP_TEST_GITLEAKS_IMAGE", "")
        docker = shutil.which("docker")
        if not image or docker is None:
            pytest.skip("gitleaks not on PATH and AIP_TEST_GITLEAKS_IMAGE not set")
        argv = [docker, "run", "--rm", "-v", f"{directory}:/scan:ro", image,
                "dir", "--no-banner", "--redact", "/scan"]  # fmt: skip
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _fake_aws_key() -> str:
    return "AKIA" + "".join(secrets.choice(BASE32) for _ in range(16))


def test_clean_directory_passes(tmp_path: Path) -> None:
    (tmp_path / "settings.py").write_text('REGION = "ap-southeast-2"\n', encoding="utf-8")
    result = _gitleaks_dir(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_planted_aws_key_fails(tmp_path: Path) -> None:
    (tmp_path / "settings.py").write_text(
        f'AWS_ACCESS_KEY_ID = "{_fake_aws_key()}"\n', encoding="utf-8"
    )
    result = _gitleaks_dir(tmp_path)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "leaks found" in (result.stdout + result.stderr)
