"""Module registry: discovery, dependency ordering, mounting and the module map (ARCH-02)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from aip.main import create_app
from aip.platform.modules.registry import (
    CycleError,
    ManifestError,
    MissingDependencyError,
    discover,
    load_modules,
    parse_disabled,
    sort_modules,
)

API_DIR = Path(__file__).resolve().parents[3]
ROOT = API_DIR.parents[1]
GEN_MODULE_MAP = ROOT / "tools" / "gen_module_map.py"
COMMITTED_MAP = ROOT / "docs" / "architecture" / "module-map.md"

FIXTURES = "tests.platform.modules.fixtures"
OK = f"{FIXTURES}.ok"
GHOST = f"{FIXTURES}.ghost"
CYCLE = f"{FIXTURES}.cycle"


def _env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIP_")}
    pythonpath = [str(API_DIR), env.get("PYTHONPATH", "")]
    env["PYTHONPATH"] = os.pathsep.join(p for p in pythonpath if p)
    env.update(extra)
    return env


# --- sort_modules (unit) ------------------------------------------------------------------------


def test_sort_puts_dependencies_first() -> None:
    assert sort_modules({"a": ["b"], "b": []}) == ["b", "a"]


def test_sort_breaks_ties_alphabetically() -> None:
    assert sort_modules({"c": [], "a": [], "b": []}) == ["a", "b", "c"]


def test_sort_is_deterministic_for_a_diamond() -> None:
    graph = {"top": ["right", "left"], "left": ["base"], "right": ["base"], "base": []}
    assert sort_modules(graph) == ["base", "left", "right", "top"]


def test_sort_rejects_a_cycle_naming_both_modules() -> None:
    with pytest.raises(CycleError) as exc:
        sort_modules({"a": ["b"], "b": ["a"]})
    message = str(exc.value)
    assert "a" in message and "b" in message
    assert "a -> b -> a" in message


def test_sort_names_only_cycle_members() -> None:
    with pytest.raises(CycleError) as exc:
        sort_modules({"x": ["y"], "y": ["z"], "z": ["y"], "free": []})
    message = str(exc.value)
    assert "y -> z -> y" in message
    assert "free" not in message


def test_sort_rejects_a_self_dependency() -> None:
    with pytest.raises(CycleError, match="a -> a"):
        sort_modules({"a": ["a"]})


def test_sort_rejects_an_unknown_dependency() -> None:
    with pytest.raises(MissingDependencyError) as exc:
        sort_modules({"a": ["ghost"]})
    assert str(exc.value) == "module a depends on unknown module ghost"


def test_parse_disabled() -> None:
    assert parse_disabled(None) == frozenset()
    assert parse_disabled("") == frozenset()
    assert parse_disabled(" ok_a , ,ok_b") == frozenset({"ok_a", "ok_b"})


# --- discover / load_modules --------------------------------------------------------------------


def test_discover_finds_fixture_modules() -> None:
    modules = discover(OK)
    assert [m.id for m in modules] == ["ok_a", "ok_b", "ok_c"]
    assert modules[0].manifest.depends_on == ["ok_b"]


def test_discover_real_package_skips_template() -> None:
    assert "_template" not in [m.id for m in discover()]
    assert "__module__" not in [m.id for m in discover()]


def test_load_modules_orders_by_dependency() -> None:
    assert [m.id for m in load_modules(OK, disabled=())] == ["ok_c", "ok_b", "ok_a"]


def test_load_modules_skips_a_disabled_leaf() -> None:
    assert [m.id for m in load_modules(OK, disabled={"ok_a"})] == ["ok_c", "ok_b"]


def test_disabling_a_needed_dependency_fails() -> None:
    with pytest.raises(MissingDependencyError, match="module ok_a depends on module ok_b"):
        load_modules(OK, disabled={"ok_b"})


def test_load_modules_reads_disabled_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIP_DISABLED_MODULES", "ok_a")
    assert [m.id for m in load_modules(OK)] == ["ok_c", "ok_b"]


def test_ghost_dependency_fails() -> None:
    with pytest.raises(MissingDependencyError) as exc:
        load_modules(GHOST, disabled=())
    assert str(exc.value) == "module ghost_dep depends on unknown module ghost"


def test_cycle_fails() -> None:
    with pytest.raises(CycleError) as exc:
        load_modules(CYCLE, disabled=())
    assert "cycle_a" in str(exc.value) and "cycle_b" in str(exc.value)


def _make_package(root: Path, name: str, manifest: str, routes: str | None) -> None:
    pkg = root / "regpkg" / name
    pkg.mkdir(parents=True)
    (root / "regpkg" / "__init__.py").touch()
    (pkg / "__init__.py").touch()
    (pkg / "manifest.toml").write_text(manifest)
    if routes is not None:
        (pkg / "routes.py").write_text(routes)


ROUTES_OK = "from fastapi import APIRouter\nrouter = APIRouter()\n"


@pytest.fixture
def tmp_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in [m for m in sys.modules if m == "regpkg" or m.startswith("regpkg.")]:
        monkeypatch.delitem(sys.modules, name)
    return tmp_path


def test_invalid_manifest_fails(tmp_package: Path) -> None:
    _make_package(tmp_package, "bad", 'id = "bad"\n', ROUTES_OK)  # no context
    with pytest.raises(ManifestError, match="bad"):
        discover("regpkg")


def test_manifest_id_must_match_folder(tmp_package: Path) -> None:
    _make_package(tmp_package, "folder", 'id = "other"\ncontext = "t"\n', ROUTES_OK)
    with pytest.raises(ManifestError, match="folder"):
        discover("regpkg")


def test_module_without_router_fails(tmp_package: Path) -> None:
    _make_package(tmp_package, "norouter", 'id = "norouter"\ncontext = "t"\n', "x = 1\n")
    with pytest.raises(ManifestError, match="norouter"):
        discover("regpkg")


# --- create_app (integration) -------------------------------------------------------------------


async def test_platform_modules_endpoint_lists_mount_order() -> None:
    app = create_app(modules_package=OK)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/platform/modules")
        assert response.status_code == 200
        assert response.json() == [
            {"id": "ok_c", "context": "test", "depends_on": []},
            {"id": "ok_b", "context": "test", "depends_on": ["ok_c"]},
            {"id": "ok_a", "context": "test", "depends_on": ["ok_b"]},
        ]
        ping = await client.get("/api/v1/ok_a/ping")
        assert ping.json() == {"module": "ok_a"}


async def test_disabled_module_is_not_mounted() -> None:
    app = create_app(modules_package=OK, disabled_modules={"ok_a"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await client.get("/api/v1/platform/modules")
        assert [m["id"] for m in listed.json()] == ["ok_c", "ok_b"]
        assert (await client.get("/api/v1/ok_a/ping")).status_code == 404


def test_platform_modules_endpoint_is_in_openapi() -> None:
    schema = create_app(modules_package=OK).openapi()
    operation = schema["paths"]["/api/v1/platform/modules"]["get"]
    content = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert content["type"] == "array"
    assert "ModuleInfo" in content["items"]["$ref"]


def test_create_app_fails_fast_on_bad_dependencies() -> None:
    with pytest.raises(MissingDependencyError):
        create_app(modules_package=GHOST)
    with pytest.raises(CycleError):
        create_app(modules_package=CYCLE)


# --- module map ---------------------------------------------------------------------------------


def _gen_map(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GEN_MODULE_MAP), *args],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_module_map_is_deterministic(tmp_path: Path) -> None:
    first, second = tmp_path / "first.md", tmp_path / "second.md"
    assert _gen_map("--package", OK, "--output", str(first)).returncode == 0
    assert _gen_map("--package", OK, "--output", str(second)).returncode == 0
    assert first.read_bytes() == second.read_bytes()

    text = first.read_text()
    assert "| 1 | `ok_c` | test | none |" in text
    assert "| 3 | `ok_a` | test | `ok_b` |" in text
    assert "graph TD" in text
    assert "    ok_a --> ok_b" in text
    assert text.index("ok_b --> ok_c") > text.index("ok_a --> ok_b")


def test_module_map_check_detects_drift(tmp_path: Path) -> None:
    out = tmp_path / "map.md"
    out.write_text("stale\n")
    result = _gen_map("--package", OK, "--output", str(out), "--check")
    assert result.returncode == 1
    assert "out of date" in result.stderr
    assert out.read_text() == "stale\n"


def test_committed_module_map_is_up_to_date() -> None:
    result = _gen_map("--output", str(COMMITTED_MAP), "--check")
    assert result.returncode == 0, result.stderr


# --- uvicorn boot (e2e) -------------------------------------------------------------------------


def test_uvicorn_exits_non_zero_on_ghost_dependency() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "aip.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
        ],
        cwd=API_DIR,
        env=_env(AIP_MODULES_PACKAGE=GHOST),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode != 0
    assert "ghost_dep" in result.stderr
    assert "module ghost_dep depends on unknown module ghost" in result.stderr
