"""OPS-11: guard rails of the Coolify demo stack and the nginx security headers."""

from __future__ import annotations

import importlib.util
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
KEYCLOAK = ROOT / "infra" / "keycloak"
IMAGES = ROOT / "infra" / "coolify" / "images"

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
    "MOCK_IDP_ALICE_PASSWORD",
    "MOCK_IDP_BOB_PASSWORD",
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
    # Coolify copies a `:?` message into the variable as its value, so there must be none.
    assert not re.search(r"\$\{[A-Z0-9_]+:\?[^}]", text)


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
    assert "postgres-data-v2:/var/lib/postgresql/data" in services["postgres"]["volumes"]
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


HSTS = 'add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;'


@pytest.mark.parametrize("conf", NGINX_CONFS, ids=lambda p: str(p.relative_to(ROOT)))
def test_nginx_sends_hsts_on_every_response(conf: Path) -> None:
    # SECURITY-11 Part B (review 11 M2, ADR 0026): TLS ends in front of both servers, so nginx
    # sends HSTS at server level and in every location that drops the inherited headers.
    text = conf.read_text()
    assert HSTS in text.split("\n    location", 1)[0]
    for path, body in re.findall(r"location ([^{]+)\{(.*?)\n    \}", text, flags=re.S):
        if "add_header" in body:
            assert HSTS in body, path.strip()


def test_the_keycloak_console_is_not_public() -> None:
    text = (ROOT / "infra" / "coolify" / "nginx.conf").read_text()
    assert "location /auth/admin/ {\n        return 404;" in text
    assert "location = /auth/admin {\n        return 404;" in text
    # Everything under /auth/ is 404 unless the allowlist regex (the demo realms, static resources)
    # matches; the master realm is never public.
    assert "location /auth/ {\n        return 404;" in text
    for public in (
        "/auth/realms/aip/protocol/openid-connect/auth",
        "/auth/realms/mock-idp/protocol/openid-connect/auth",
        "/auth/resources/x/login.css",
    ):
        assert _first_regex_location(text, public) == "proxy", public
    for private in ("/auth/realms/master/protocol/openid-connect/token", "/auth/admin/master/"):
        assert _first_regex_location(text, private) is None, private


def _first_regex_location(text: str, path: str) -> str | None:
    """How the first regex location matching ``path`` answers, as nginx picks it (config order).

    ``"404"`` for ``return 404``, ``"proxy"`` for ``proxy_pass``, ``None`` when no regex location
    matches (the ``/auth/`` prefix location then answers 404).
    """
    for pattern, body in re.findall(r"location ~ (\S+) \{(.*?)\n    \}", text, flags=re.S):
        if re.match(pattern, path):
            return "404" if "return 404;" in body else "proxy" if "proxy_pass" in body else body
    return None


def test_the_mock_idp_account_console_is_not_public() -> None:
    # Review 11 H1: the demo users' passwords are in the public repo and both brokers trust the
    # mock IdP's emails, so its account console (change email) must not be reachable.
    text = (ROOT / "infra" / "coolify" / "nginx.conf").read_text()
    for private in (
        "/auth/realms/mock-idp/account",
        "/auth/realms/mock-idp/account/",
        "/auth/realms/mock-idp/account/credentials",
        "/auth/realms/mock-idp/account;x=1",
    ):
        assert _first_regex_location(text, private) == "404", private
    # Sign-in through the mock IdP still works.
    for public in (
        "/auth/realms/mock-idp/protocol/openid-connect/auth",
        "/auth/realms/mock-idp/login-actions/authenticate",
        "/auth/realms/mock-idp/broker/x/endpoint",
    ):
        assert _first_regex_location(text, public) == "proxy", public


@pytest.mark.parametrize(
    ("conf", "upstreams"),
    [(ROOT / "infra" / "coolify" / "nginx.conf", 2), (ROOT / "apps" / "web" / "nginx.conf", 1)],
    ids=["coolify", "web"],
)
def test_upstreams_get_one_client_address_not_the_client_list(conf: Path, upstreams: int) -> None:
    # Review 11 M1: both web servers resolve the client through realip (private hops only) and
    # pass on that one address, so a client-supplied X-Forwarded-For never reaches the API.
    text = conf.read_text()
    assert "$proxy_add_x_forwarded_for" not in text
    for line in (
        "set_real_ip_from 10.0.0.0/8;",
        "set_real_ip_from 172.16.0.0/12;",
        "set_real_ip_from 192.168.0.0/16;",
        "real_ip_header X-Forwarded-For;",
        "real_ip_recursive on;",
    ):
        assert line in text, line
    assert "set_real_ip_from 0.0.0.0/0;" not in text
    assert text.count("proxy_set_header X-Forwarded-For $remote_addr;") == upstreams


def test_the_api_trusts_forwarded_headers_from_private_hops_only() -> None:
    api = yaml.safe_load(COMPOSE.read_text())["services"]["api"]
    assert "--proxy-headers" in api["command"]
    assert not any(str(arg).startswith("--forwarded-allow-ips") for arg in api["command"])
    assert api["environment"]["FORWARDED_ALLOW_IPS"] == "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


def _deployed_realms_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "deployed_realms", KEYCLOAK / "deployed_realms.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def deployed() -> dict[str, dict[str, Any]]:
    module = _deployed_realms_module()
    return {
        name: module.deployed_realm(json.loads((KEYCLOAK / name).read_text(encoding="utf-8")))
        for name in module.REALMS
    }


def test_the_deployed_mock_idp_realm_has_no_users_or_credentials(
    deployed: dict[str, dict[str, Any]],
) -> None:
    # SECURITY-11 Part A (review 11 H1): no demo user's password in the repo or the image.
    mock = deployed["realm-mock-idp.json"]
    assert "users" not in mock
    for name, realm in deployed.items():
        assert '"credentials": [' not in json.dumps(realm), name
        assert "dev_only_password" not in json.dumps(realm), name
    # The aip realm keeps its service-account user (aip-admin's manage-users roles).
    users = deployed["realm-aip.json"]["users"]
    assert [u["username"] for u in users] == ["service-account-aip-admin"]


def test_a_realm_user_with_credentials_is_dropped() -> None:
    module = _deployed_realms_module()
    realm = {
        "users": [
            {"username": "x", "credentials": [{"type": "password", "value": "p"}]},
            {"username": "service-account-y", "serviceAccountClientId": "y"},
        ]
    }
    assert module.deployed_realm(realm)["users"] == [
        {"username": "service-account-y", "serviceAccountClientId": "y"}
    ]
    assert "users" not in module.deployed_realm({"users": [realm["users"][0]]})


def test_the_deployed_realms_have_no_client_secret_defaults(
    deployed: dict[str, dict[str, Any]],
) -> None:
    # SECURITY-11 Part D (review 11 M4): an import without the env var must not get a public secret.
    for name, realm in deployed.items():
        text = json.dumps(realm)
        assert not re.search(r"\$\{[A-Z0-9_]*SECRET:", text), name
        assert "dev_only_secret" not in text, name
    aip = {c["clientId"]: c for c in deployed["realm-aip.json"]["clients"]}
    assert aip["aip-api"]["secret"] == "${AIP_API_CLIENT_SECRET}"
    assert aip["aip-admin"]["secret"] == "${AIP_ADMIN_CLIENT_SECRET}"
    # Non-secret defaults (URLs, SMTP host) stay.
    assert "${APP_ORIGIN:http://localhost:8080}" in json.dumps(deployed["realm-aip.json"])


def test_a_secret_default_added_to_a_realm_is_stripped() -> None:
    module = _deployed_realms_module()
    realm = {"clients": [{"secret": "${NEW_CLIENT_SECRET:public}"}], "x": "${OTHER:keep}"}
    assert module.deployed_realm(realm) == {
        "clients": [{"secret": "${NEW_CLIENT_SECRET}"}],
        "x": "${OTHER:keep}",
    }


def test_the_demo_image_imports_the_deployed_realms_and_guards_its_secrets() -> None:
    dockerfile = (IMAGES / "keycloak.Dockerfile").read_text()
    assert "RUN python3 /src/deployed_realms.py /out" in dockerfile
    assert (
        "COPY --from=realms /out/realm-aip.json /out/realm-mock-idp.json /opt/keycloak/data/import/"
        in dockerfile
    )
    # The dev realm files are only an input of the build stage, never copied into Keycloak.
    keycloak_stage = dockerfile.split("FROM quay.io/keycloak/keycloak", 1)[1]
    assert "infra/keycloak/realm-" not in keycloak_stage
    assert 'ENTRYPOINT ["/opt/keycloak/aip/keycloak-entrypoint.sh"]' in dockerfile
    # The entrypoint knows every dev client-secret default of the dev realms.
    entrypoint = (IMAGES / "keycloak-entrypoint.sh").read_text()
    dev_defaults = set()
    for name in ("realm-aip.json", "realm-mock-idp.json"):
        text = (KEYCLOAK / name).read_text(encoding="utf-8")
        dev_defaults |= set(re.findall(r"\$\{([A-Z0-9_]*_CLIENT_SECRET):([^}]*)\}", text))
    assert dev_defaults
    for var, value in dev_defaults:
        assert f"[{var}]={value}" in entrypoint, var


def test_the_mock_idp_users_come_from_secrets_before_web_starts(
    services: dict[str, dict[str, Any]],
) -> None:
    users = services["mock-idp-users"]
    assert users["entrypoint"] == ["/opt/keycloak/aip/mock-idp-users.sh"]
    assert users["depends_on"]["keycloak"]["condition"] == "service_healthy"
    assert users["environment"]["MOCK_IDP_ALICE_PASSWORD"] == "${MOCK_IDP_ALICE_PASSWORD:?}"
    assert users["environment"]["MOCK_IDP_BOB_PASSWORD"] == "${MOCK_IDP_BOB_PASSWORD:?}"
    assert (
        services["web"]["depends_on"]["mock-idp-users"]["condition"]
        == "service_completed_successfully"
    )
    script = (IMAGES / "mock-idp-users.sh").read_text()
    assert ': "${MOCK_IDP_ALICE_PASSWORD:?}"' in script
    assert "alice_dev_only_password | bob_dev_only_password" in script
