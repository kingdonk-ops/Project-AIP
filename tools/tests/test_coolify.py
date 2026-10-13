"""OPS-11: guard rails of the Coolify demo stack and the nginx security headers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "coolify" / "docker-compose.coolify.yml"
ENV_EXAMPLE = ROOT / "infra" / "coolify" / "env.example"
HEADERS = json.loads((ROOT / "apps" / "web" / "security-headers.json").read_text())["headers"]
NGINX_CONFS = [ROOT / "apps" / "web" / "nginx.conf", ROOT / "infra" / "coolify" / "nginx.conf"]

SECRETS = {
    "POSTGRES_PASSWORD",
    "AIP_OWNER_PASSWORD",
    "AIP_APP_PASSWORD",
    "AIP_JOBS_PASSWORD",
    "KEYCLOAK_DB_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "AIP_API_CLIENT_SECRET",
    "AIP_ADMIN_CLIENT_SECRET",
    "MOCK_IDP_CLIENT_SECRET",
    "OBJECT_STORE_ACCESS_KEY_ID",
    "OBJECT_STORE_SECRET_ACCESS_KEY",
    "PREAUTH_COOKIE_KEY",
    "PROJECTS_CURSOR_KEY",
}


def _uncommented(path: Path) -> str:
    return "\n".join(
        line.split(" #", 1)[0]
        for line in path.read_text().splitlines()
        if not line.lstrip().startswith("#")
    )


@pytest.fixture(scope="module")
def services() -> dict[str, dict[str, Any]]:
    return yaml.safe_load(COMPOSE.read_text())["services"]


def test_no_service_publishes_a_host_port(services: dict[str, dict[str, Any]]) -> None:
    assert [name for name, s in services.items() if "ports" in s] == []
    assert [name for name, s in services.items() if "expose" in s] == ["web"]


def test_secrets_are_required_and_have_no_default() -> None:
    text = _uncommented(COMPOSE)
    for name in SECRETS:
        uses = re.findall(r"\$\{" + name + r"(:[?-][^}]*)?\}", text)
        assert uses, f"{name} is not used"
        assert all(u.startswith(":?") for u in uses), f"{name} must be ${{{name}:?...}} everywhere"


def test_env_example_lists_every_variable_with_dummy_values() -> None:
    used = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", _uncommented(COMPOSE)))
    lines = [ln for ln in ENV_EXAMPLE.read_text().splitlines() if ln and not ln.startswith("#")]
    listed = {ln.split("=", 1)[0]: ln.split("=", 1)[1] for ln in lines}
    assert used <= set(listed), f"missing from env.example: {sorted(used - set(listed))}"
    for name in SECRETS:
        assert "change-me" in listed[name] or "replace-with" in listed[name], name


def test_every_app_service_runs_as_demo(services: dict[str, dict[str, Any]]) -> None:
    for name, service in services.items():
        env = service.get("environment") or {}
        if "AIP_ENV" in env:
            assert env["AIP_ENV"] == "demo", name
    assert services["api"]["environment"]["AIP_ENV"] == "demo"


def test_data_lives_in_named_volumes_and_is_backed_up(services: dict[str, dict[str, Any]]) -> None:
    assert "postgres-data:/var/lib/postgresql/data" in services["postgres"]["volumes"]
    assert "rustfs-data:/data" in services["rustfs"]["volumes"]
    backup = services["postgres-backup"]
    assert (
        "pg_dump" in " ".join(backup["command"])
        and "postgres-backups:/backups" in backup["volumes"]
    )


def test_no_service_bind_mounts_a_repository_file(services: dict[str, dict[str, Any]]) -> None:
    # Coolify resolves relative mount paths under the app's directory on the server, not the clone,
    # so a repository file would mount empty (the first demo deploy failed that way). Only named
    # volumes are allowed; config is built into the images.
    for name, svc in services.items():
        for volume in svc.get("volumes", []):
            source = (
                volume.split(":", 1)[0] if isinstance(volume, str) else volume.get("source", "")
            )
            assert not source.startswith((".", "/")), f"{name} bind-mounts {source}"


def test_every_ghcr_image_is_built_by_the_workflow(services: dict[str, dict[str, Any]]) -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-coolify.yml").read_text()
    built = set(re.findall(r"^\s*build (aip-[a-z-]+) ", workflow, flags=re.M))
    used = {
        m.group(1)
        for svc in services.values()
        if (m := re.search(r"/(aip-[a-z-]+):", svc["image"]))
    }
    assert used == built, f"used {sorted(used)}, built {sorted(built)}"


def test_the_bootstrap_runs_before_the_migrator_and_keycloak(
    services: dict[str, dict[str, Any]],
) -> None:
    assert services["db-bootstrap"]["command"] == ["/aip/db-bootstrap.sh"]
    for name in ("migrator", "keycloak"):
        assert (
            services[name]["depends_on"]["db-bootstrap"]["condition"]
            == "service_completed_successfully"
        )


def test_api_waits_for_the_migrator(services: dict[str, dict[str, Any]]) -> None:
    for name in ("api", "worker"):
        assert (
            services[name]["depends_on"]["migrator"]["condition"]
            == "service_completed_successfully"
        )


@pytest.mark.parametrize("conf", NGINX_CONFS, ids=lambda p: str(p.relative_to(ROOT)))
def test_nginx_repeats_every_security_header(conf: Path) -> None:
    text = conf.read_text()
    server_level = text.split("\n    location", 1)[0]
    for name, value in HEADERS.items():
        assert f'add_header {name} "{value}" always;' in server_level, f"server: {name}"
    for block in re.findall(r"location ([^{]+)\{(.*?)\n    \}", text, flags=re.S):
        path, body = block
        if "add_header" not in body:
            continue  # inherits the server-level set
        for name, value in HEADERS.items():
            if path.strip().startswith("~ ^/auth/") and name == "Content-Security-Policy":
                continue  # Keycloak sends its own CSP for its pages
            assert f'add_header {name} "{value}" always;' in body, f"{path.strip()}: {name}"


def test_the_keycloak_console_is_not_public() -> None:
    text = (ROOT / "infra" / "coolify" / "nginx.conf").read_text()
    assert "location /auth/admin/ {\n        return 404;" in text
    assert "location = /auth/admin {\n        return 404;" in text
    # Everything under /auth/ is 404 unless the allowlist regex (the demo realms, static resources)
    # matches; the master realm is never public.
    assert "location /auth/ {\n        return 404;" in text
    allow = re.search(r"location ~ (\S+) \{", text)
    assert allow is not None
    pattern = re.compile(allow.group(1))
    for public in ("/auth/realms/aip/protocol/openid-connect/auth", "/auth/resources/x/login.css"):
        assert pattern.match(public), public
    for private in ("/auth/realms/master/protocol/openid-connect/token", "/auth/admin/master/"):
        assert not pattern.match(private), private


def test_upstreams_get_one_client_address_not_the_client_list() -> None:
    text = (ROOT / "infra" / "coolify" / "nginx.conf").read_text()
    assert "$proxy_add_x_forwarded_for" not in text
    assert "real_ip_recursive on;" in text
    assert text.count("proxy_set_header X-Forwarded-For $remote_addr;") == 2
