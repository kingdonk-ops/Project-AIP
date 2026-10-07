"""Static checks on the docker-compose stack (STACK-05).

The stack itself runs in the CI ``compose`` job (``up --wait``, UID checks, version and render
e2e). These tests catch the mistakes that job would only find after minutes of image pulls: an
unpinned or non-permissive image, a missing healthcheck, an app container that could run as root,
an undocumented variable, and ``docker compose config`` rejecting the file.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "docker-compose.yml"
ENV_EXAMPLE = ROOT / ".env.example"

# Images built from this repo: UID 10001, read-only root, no capabilities (step 2).
APP_SERVICES = {"api", "worker", "migrator", "object-store-init", "web", "sandbox"}
# One-shot jobs: they exit 0 and their dependents wait on service_completed_successfully.
ONE_SHOT = {"migrator", "object-store-init"}
DEFAULT_SERVICES = {
    "postgres",
    "valkey",
    "rustfs",
    "gotenberg",
    "keycloak",
    "migrator",
    "object-store-init",
    "api",
    "worker",
    "web",
}
REQUIRED_ENV = {
    "DATABASE_URL",
    "DATABASE_MIGRATOR_URL",
    "DATABASE_JOBS_URL",
    "REDIS_URL",
    "OBJECT_STORE",
    "PDF_RENDERER",
    "GIT_SHA",
    "BUILD_ID",
}
ROOT_USERS = {"root", "0", "0:0", "root:root"}


def _load() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return _load()


@pytest.fixture(scope="module")
def services(compose: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return compose["services"]


def _default(services: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {name: svc for name, svc in services.items() if not svc.get("profiles")}


def test_default_profile_has_the_expected_services(services: dict[str, dict[str, Any]]) -> None:
    assert set(_default(services)) == DEFAULT_SERVICES
    assert services["sandbox"]["profiles"] == ["sandbox"]


def test_images_are_pinned_and_permissive(services: dict[str, dict[str, Any]]) -> None:
    for name, svc in services.items():
        if "build" in svc:
            continue
        image = svc.get("image")
        assert isinstance(image, str), f"{name}: needs an image or a build"
        repo, _, tag = image.rpartition(":")
        assert repo and tag, f"{name}: {image} has no tag"
        assert tag not in {"latest", "stable", "edge", "main", "dev"}, f"{name}: floating tag"
        assert re.search(r"\d+\.\d+", tag), f"{name}: {image} is not pinned to a version"
        # Redis server 7.4+ is not permissively licensed; Valkey (BSD-3) replaces it.
        assert not re.match(r"^(docker\.io/)?(library/)?redis(/|$)", repo), f"{name}: use Valkey"


def test_postgres_is_16_with_pgvector(services: dict[str, dict[str, Any]]) -> None:
    assert re.fullmatch(r"pgvector/pgvector:[\d.]+-pg16(-\w+)?", services["postgres"]["image"])


def test_every_long_running_service_has_a_healthcheck(
    services: dict[str, dict[str, Any]],
) -> None:
    for name, svc in services.items():
        if name in ONE_SHOT or name == "sandbox":
            continue
        check = svc.get("healthcheck")
        assert check and check.get("test"), f"{name}: no healthcheck"
        assert not check.get("disable"), f"{name}: healthcheck disabled"


def test_api_healthcheck_curls_ready(services: dict[str, dict[str, Any]]) -> None:
    test = services["api"]["healthcheck"]["test"]
    joined = " ".join(test) if isinstance(test, list) else test
    assert "curl" in joined
    assert "/api/v1/health/ready" in joined


def test_one_shots_gate_their_dependents(services: dict[str, dict[str, Any]]) -> None:
    for name in ("api", "worker"):
        depends = services[name]["depends_on"]
        assert depends["migrator"]["condition"] == "service_completed_successfully", name
    assert (
        services["api"]["depends_on"]["object-store-init"]["condition"]
        == "service_completed_successfully"
    )
    for name in ONE_SHOT:
        assert services[name].get("restart", "no") == "no", name
    assert services["migrator"]["depends_on"]["postgres"]["condition"] == "service_healthy"


def test_api_runs_uvicorn_factory(services: dict[str, dict[str, Any]]) -> None:
    command = services["api"]["command"]
    assert command[:3] == ["uvicorn", "aip.main:create_app", "--factory"]
    assert services["worker"]["build"] == services["api"]["build"], "one image for api and worker"


def test_app_images_are_hardened(services: dict[str, dict[str, Any]]) -> None:
    for name in APP_SERVICES:
        svc = services[name]
        assert str(svc.get("user")) == "10001:10001", f"{name}: user"
        assert svc.get("read_only") is True, f"{name}: read_only"
        assert svc.get("cap_drop") == ["ALL"], f"{name}: cap_drop"
        assert "no-new-privileges:true" in svc.get("security_opt", []), f"{name}: no-new-privs"
        assert any(str(t).startswith("/tmp") for t in svc.get("tmpfs", [])), f"{name}: tmpfs"
    assert services["sandbox"]["network_mode"] == "none"


def test_no_service_runs_as_root(services: dict[str, dict[str, Any]]) -> None:
    for name, svc in _default(services).items():
        user = svc.get("user")
        assert user is not None, f"{name}: set an explicit non-root user"
        assert str(user) not in ROOT_USERS, f"{name}: runs as root"


def test_published_ports_bind_to_localhost(services: dict[str, dict[str, Any]]) -> None:
    for name, svc in services.items():
        for port in svc.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name}: {port} is exposed beyond localhost"


def _compose_variables() -> set[str]:
    text = COMPOSE.read_text(encoding="utf-8")
    return set(re.findall(r"\$\{([A-Z0-9_]+)", text))


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        assert sep, f".env.example: not KEY=value: {line}"
        values[key.strip()] = value.strip()
    return values


def test_env_example_documents_every_variable() -> None:
    documented = set(_env_example())
    missing = (_compose_variables() | REQUIRED_ENV) - documented
    assert not missing, f".env.example is missing {sorted(missing)}"


def test_env_example_holds_placeholders_only() -> None:
    for key, value in _env_example().items():
        if re.search(r"PASSWORD|SECRET|_KEY$|TOKEN", key) and value:
            # Placeholders only: obviously fake dev values, never a real credential.
            assert re.search(r"dev|change|example|placeholder|local", value), f"{key}={value}"


def test_every_compose_default_is_documented_with_the_same_value() -> None:
    """``${VAR:-default}`` in compose and ``VAR=`` in .env.example must agree."""
    documented = _env_example()
    text = COMPOSE.read_text(encoding="utf-8")
    for var, default in re.findall(r"\$\{([A-Z0-9_]+):-([^}]*)\}", text):
        if documented.get(var):
            assert documented[var] == default, f"{var}: compose {default!r} vs .env.example"


@pytest.mark.skipif(
    shutil.which("docker") is None
    or subprocess.run(["docker", "compose", "version"], capture_output=True).returncode != 0,
    reason="needs the docker compose CLI (no daemon required)",
)
def test_docker_compose_config_accepts_the_file() -> None:
    for profiles in ([], ["--profile", "sandbox"]):
        result = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE), *profiles, "config", "--quiet"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
