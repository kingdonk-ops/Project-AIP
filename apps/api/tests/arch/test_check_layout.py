"""``tools/ci/check_layout.py``: the ADR 0004 repository layout."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "tools" / "ci" / "check_layout.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_layout", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_layout = _load().check_layout


def test_services_path_gives_one_error() -> None:
    errors = check_layout(["services/sidecar/main.py"])
    assert len(errors) == 1, errors
    assert "services/" in errors[0]


def test_backend_and_frontend_paths_fail() -> None:
    errors = check_layout(["backend/x.py", "frontend/app.tsx"])
    assert len(errors) == 2, errors
    assert "backend/" in errors[0]
    assert "frontend/" in errors[1]


def test_typescript_and_package_json_under_api_fail() -> None:
    errors = check_layout(
        ["apps/api/foo.ts", "apps/api/ui/x.tsx", "apps/api/lib/y.mts", "apps/api/package.json"]
    )
    assert len(errors) == 4, errors
    assert "apps/api/foo.ts" in errors[0]


def test_python_under_packages_fails() -> None:
    errors = check_layout(["packages/ui/gen.py"])
    assert len(errors) == 1, errors
    assert "packages/ui/gen.py" in errors[0]


def test_allowed_paths_pass() -> None:
    assert (
        check_layout(
            [
                "apps/api/aip/main.py",
                "apps/web/src/main.tsx",
                "packages/ui/package.json",
                "tools/ci/check_layout.py",
                "apps/api/aip/services/x.py",  # only a top-level services/ is forbidden
                "docs/backend/notes.md",
            ]
        )
        == []
    )


def test_cli_on_real_repo_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
