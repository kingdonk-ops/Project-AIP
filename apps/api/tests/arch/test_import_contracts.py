"""Import-boundary contracts run by ``lint-imports`` (ARCH-03, ADR 0004)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2]
ROOT = API_DIR.parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LINT_IMPORTS = str(Path(sys.executable).with_name("lint-imports"))


def _lint_imports(*args: str, pythonpath: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if pythonpath is not None:
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(pythonpath), env.get("PYTHONPATH", "")) if p
        )
    # Run from the repo root: lint-imports puts the cwd on sys.path, which is how the custom
    # contract type (tools.ci.importlinter_contracts) is found.
    return subprocess.run(
        [LINT_IMPORTS, "--no-cache", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _broken(output: str) -> list[str]:
    return [line.split()[0] for line in output.splitlines() if line.rstrip().endswith("BROKEN")]


def test_deep_import_breaks_only_no_deep_module_import() -> None:
    fixture = FIXTURES / "deep_import"
    result = _lint_imports("--config", str(fixture / ".importlinter"), pythonpath=fixture)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert _broken(output) == ["no-deep-module-import"], output
    assert "deep_app.modules.a.service -> deep_app.modules.b.service" in output
    # The module package itself and its api stay allowed (a/allowed.py).
    assert "deep_app.modules.a.allowed ->" not in output


def test_platform_importing_a_module_breaks_platform_contract() -> None:
    fixture = FIXTURES / "platform_imports_module"
    result = _lint_imports("--config", str(fixture / ".importlinter"), pythonpath=fixture)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert _broken(output) == ["platform-never-imports-modules"], output


def test_real_repo_keeps_every_contract() -> None:
    result = _lint_imports()
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "no-deep-module-import KEPT" in output
    assert "platform-never-imports-modules KEPT" in output
