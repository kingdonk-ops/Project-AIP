"""``tools/ci/check_manifests.py``: code-used permissions, events and term keys are declared."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "tools" / "ci" / "check_manifests.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_manifests", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_manifests = _load().check_manifests


def test_undeclared_event_gives_exactly_one_error() -> None:
    errors = check_manifests(FIXTURES / "undeclared_event")
    assert len(errors) == 1, errors
    assert "x.y.z" in errors[0]
    assert "events" in errors[0]


def test_clean_module_has_no_errors() -> None:
    assert check_manifests(FIXTURES / "clean") == []


def test_undeclared_permission_and_term(tmp_path: Path) -> None:
    module = tmp_path / "things"
    module.mkdir()
    (module / "manifest.toml").write_text('id = "things"\ncontext = "x"\n')
    (module / "routes.py").write_text(
        "from x import access, term\n"
        "dep = access.require_permission('things.thing.read')\n"
        "label = term('things.thing.label')\n"
    )
    errors = check_manifests(tmp_path)
    assert len(errors) == 2, errors
    assert any("things.thing.read" in e and "permissions" in e for e in errors)
    assert any("things.thing.label" in e and "term_keys" in e for e in errors)


def test_module_tests_and_template_are_skipped(tmp_path: Path) -> None:
    for name in ("real", "_template"):
        module = tmp_path / name
        (module / "tests").mkdir(parents=True)
        (module / "manifest.toml").write_text(f'id = "{name}"\ncontext = "x"\n')
        (module / "tests" / "test_x.py").write_text("emit(None, 'test.only', 1, {})\n")
    (tmp_path / "_template" / "service.py").write_text("emit(None, 'a.b', 1, {})\n")
    assert check_manifests(tmp_path) == []


def test_missing_manifest_and_syntax_error_are_reported(tmp_path: Path) -> None:
    (tmp_path / "nomanifest").mkdir()
    (tmp_path / "nomanifest" / "__init__.py").write_text("")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "manifest.toml").write_text('id = "broken"\ncontext = "x"\n')
    (broken / "service.py").write_text("def (:\n")
    errors = check_manifests(tmp_path)
    assert any("nomanifest" in e and "manifest.toml" in e for e in errors), errors
    assert any("service.py" in e and "syntax" in e.lower() for e in errors), errors


def test_cli_on_real_modules_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_on_fixture_exits_one() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES / "undeclared_event")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "x.y.z" in result.stdout
