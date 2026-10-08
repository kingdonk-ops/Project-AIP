"""Production strip test (SECURITY-08): dev tooling, test code and debug routes never ship.

The manifest is config/prod-strip-manifest.txt; the checker is tools/ci/check_prod_strip.py.

Always run:
- the manifest parser returns the five forbidden entries;
- the app built for production (and with no AIP_ENV) mounts no debug route, and the same check
  catches the route when AIP_ENV=test (positive control);
- the checker fails this dev environment (pytest importable, tests in the package): the negative
  control that proves the in-image check can fail.

Image tests (CI: .github/workflows/security.yml; locally `make strip-check`) run when the images
are named in the environment, and are skipped otherwise:
- AIP_TEST_API_IMAGE      the production API image (apps/api/Dockerfile, default target)
- AIP_TEST_API_DEV_IMAGE  the same Dockerfile built with --target dev (negative control)
- AIP_TEST_WEB_IMAGE      the production web image (apps/web/Dockerfile)
- AIP_TEST_WEB_DIST / AIP_TEST_WEB_DEV_DIST  a production and a development Vite build output
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

from aip.main import create_app

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "tools" / "ci" / "check_prod_strip.py"

FORBIDDEN = [
    "aip.fixtures.admin",
    "aip.modules.architecture_map",
    "aip.modules.module_builder",
    "aip.modules.pipelines",
    "aip.modules.compliance_dsl",
]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_prod_strip", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_prod_strip"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


cps = _load()
MANIFEST = cps.load_manifest()


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        pytest.skip(f"{name} not set (built and set by .github/workflows/security.yml)")
    return value


def _docker() -> str:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker not on PATH")
    return docker


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def _route_paths(env: str) -> list[str]:
    app = create_app(env=env, tracing=False)
    return cps.route_paths(app.routes) + list(app.openapi()["paths"])


# --- unit ----------------------------------------------------------------------------------------


def test_manifest_parser_returns_the_five_forbidden_entries() -> None:
    assert [e.value for e in MANIFEST.forbidden] == FORBIDDEN


@pytest.mark.parametrize("env", ["production", "", "development"])
def test_non_test_app_mounts_no_debug_route(env: str) -> None:
    assert cps.check_routes(_route_paths(env), MANIFEST.routes, env) == []


def test_route_walk_finds_the_api_routes() -> None:
    paths = _route_paths("production")
    assert "/api/v1/health" in paths
    assert "/api/v1/health/ready" in paths
    assert "/api/v1/platform/version" in paths


def test_route_check_catches_the_test_only_route() -> None:
    errors = cps.check_routes(_route_paths("test"), MANIFEST.routes, "test")
    assert any("/api/v1/_debug/context" in e for e in errors), errors


def test_strip_check_fails_the_dev_environment() -> None:
    # Negative control: pytest is importable here and apps/api/aip still holds tests and the
    # module template, so the same check that runs inside the image must report them.
    errors = cps.api_env_errors(MANIFEST, image_paths=False)
    joined = "\n".join(errors)
    assert "pytest: importable" in joined
    assert "aip.modules._template" in joined
    assert "aip/modules/ops/tests" in joined


# --- integration: the API image ------------------------------------------------------------------


def test_prod_api_image_passes_the_strip_check() -> None:
    _docker()
    result = _cli("api-image", _env("AIP_TEST_API_IMAGE"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "is clean" in result.stdout


@pytest.mark.parametrize("module", FORBIDDEN)
def test_forbidden_import_raises_import_error_in_prod_image(module: str) -> None:
    docker = _docker()
    image = _env("AIP_TEST_API_IMAGE")
    probe = (
        f"try:\n    import {module}\nexcept ImportError as e:\n    print('ImportError', e)\n"
        "else:\n    raise SystemExit('imported')\n"
    )
    result = subprocess.run(
        [docker, "run", "--rm", "--network", "none", "--entrypoint", "python", image,
         "-I", "-c", probe],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("ImportError"), result.stdout


def test_dev_api_image_fails_the_strip_check() -> None:
    # Negative control: the dev target (dev dependency group installed) must fail.
    _docker()
    result = _cli("api-image", _env("AIP_TEST_API_DEV_IMAGE"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "pytest: importable" in result.stdout


def test_planted_forbidden_module_fails_the_strip_check() -> None:
    # Negative control: the prod image plus an empty aip.modules.module_builder package.
    docker = _docker()
    image = _env("AIP_TEST_API_IMAGE")
    planted = f"aip-strip-planted:{uuid.uuid4().hex[:12]}"
    dockerfile = (
        f"FROM {image}\nUSER root\n"
        'RUN python -I -c "import aip, pathlib; '
        "p = pathlib.Path(aip.__file__).parent / 'modules' / 'module_builder'; "
        "p.mkdir(); (p / '__init__.py').touch()\"\n"
        "USER 10001:10001\n"
    )
    subprocess.run(
        [docker, "build", "-q", "-t", planted, "-"],
        input=dockerfile, capture_output=True, text=True, check=True,
    )  # fmt: skip
    try:
        result = _cli("api-image", planted)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "aip.modules.module_builder: importable" in result.stdout
        assert "aip.modules.module_builder: present in the package" in result.stdout
    finally:
        subprocess.run([docker, "rmi", "-f", planted], capture_output=True, check=False)


# --- integration: the web build ------------------------------------------------------------------


def test_prod_web_image_passes_the_strip_check() -> None:
    _docker()
    result = _cli("web-image", _env("AIP_TEST_WEB_IMAGE"))
    assert result.returncode == 0, result.stdout + result.stderr


def test_prod_web_dist_passes_the_strip_check() -> None:
    result = _cli("web-dist", _env("AIP_TEST_WEB_DIST"))
    assert result.returncode == 0, result.stdout + result.stderr


def test_dev_web_dist_fails_the_strip_check() -> None:
    # Negative control: NODE_ENV=development vite build --sourcemap ships the React dev runtime
    # and source maps.
    result = _cli("web-dist", _env("AIP_TEST_WEB_DEV_DIST"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert ".map" in result.stdout
    assert "jsxDEV" in result.stdout
