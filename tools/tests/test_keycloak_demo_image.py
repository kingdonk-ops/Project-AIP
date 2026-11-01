"""SECURITY-11 Parts A and D: the Coolify demo Keycloak image, built and run.

Builds ``infra/coolify/images/keycloak.Dockerfile`` and checks that:

- the entrypoint refuses to start without the client secrets, or with a public dev value;
- with test secrets, the deployed mock IdP has no users until ``mock-idp-users.sh`` (run exactly as
  the compose one-shot runs it) creates alice with the secret password; the committed dev password
  does not sign in.

Sign-in is checked with a password grant on the realm's built-in ``admin-cli`` client, which is what
``kcadm config credentials`` does. Needs Docker: skipped locally without it, failed under CI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "infra" / "coolify" / "images" / "keycloak.Dockerfile"
SECRETS = {
    "AIP_API_CLIENT_SECRET": "test-api-client-secret",
    "PORTAL_OIDC_CLIENT_SECRET": "test-portal-client-secret",
    "AIP_ADMIN_CLIENT_SECRET": "test-admin-client-secret",
    "MOCK_IDP_CLIENT_SECRET": "test-mock-idp-secret",
}
ADMIN_PASSWORD = "test-admin-password"
ALICE_PASSWORD = "Alice-from-the-secret-store-1"
KCADM = "/opt/keycloak/bin/kcadm.sh"


def _docker(
    *args: str, check: bool = True, timeout: float = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
    )


def _docker_works() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return _docker("info", check=False, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@pytest.fixture(scope="module")
def image() -> Iterator[str]:
    if not _docker_works():
        message = "no Docker daemon: the demo Keycloak image cannot be built"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    tag = f"aip-keycloak-demo:test-{uuid.uuid4().hex[:8]}"
    _docker("build", "-q", "-f", str(DOCKERFILE), "-t", tag, str(ROOT), timeout=1200)
    yield tag
    _docker("rmi", "-f", tag, check=False)


def _env_args(env: dict[str, str]) -> list[str]:
    return [arg for key, value in env.items() for arg in ("-e", f"{key}={value}")]


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "AIP_API_CLIENT_SECRET is not set"),
        ({**SECRETS, "MOCK_IDP_CLIENT_SECRET": ""}, "MOCK_IDP_CLIENT_SECRET is not set"),
        (
            {**SECRETS, "AIP_ADMIN_CLIENT_SECRET": "aip_admin_dev_only_secret"},
            "AIP_ADMIN_CLIENT_SECRET is the public dev value",
        ),
    ],
    ids=["no-secrets", "empty-secret", "dev-secret"],
)
def test_the_entrypoint_refuses_missing_or_dev_secrets(
    image: str, env: dict[str, str], message: str
) -> None:
    result = _docker("run", "--rm", *_env_args(env), image, "start-dev", check=False, timeout=120)
    assert result.returncode == 1, result.stdout + result.stderr
    assert message in result.stderr


@pytest.fixture(scope="module")
def keycloak(image: str) -> Iterator[tuple[str, str]]:
    """A running demo Keycloak (dev-file database) and the network it is reachable on."""
    network = f"aip-kc-test-{uuid.uuid4().hex[:8]}"
    name = f"keycloak-{network}"
    _docker("network", "create", network)
    env = {
        **SECRETS,
        "KC_BOOTSTRAP_ADMIN_USERNAME": "admin",
        "KC_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD,
        "KC_HTTP_RELATIVE_PATH": "/auth",
        "KC_HEALTH_ENABLED": "true",
        "KEYCLOAK_PUBLIC_URL": f"http://{name}:8080/auth",
        "KEYCLOAK_INTERNAL_URL": "http://localhost:8080/auth",
        "KC_SMTP_HOST": "localhost",
    }
    try:
        _docker(
            "run", "-d", "--name", name, "--network", network, *_env_args(env),
            image, "start-dev", "--import-realm",
        )  # fmt: skip
        deadline = time.monotonic() + 300
        while True:
            probe = _docker(
                "exec", name, "bash", "-c",
                "exec 3<>/dev/tcp/127.0.0.1/9000 && printf 'GET /auth/health/ready HTTP/1.1\\r\\n"
                "Host: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3 && head -n 1 <&3",
                check=False, timeout=30,
            )  # fmt: skip
            if " 200" in probe.stdout:
                break
            if time.monotonic() > deadline:
                logs = _docker("logs", name, check=False).stdout[-4000:]
                pytest.fail(f"the demo Keycloak did not become ready:\n{logs}")
            time.sleep(3)
        yield name, network
    finally:
        _docker("rm", "-f", name, check=False)
        _docker("network", "rm", network, check=False)


def _sign_in(image: str, network: str, server: str, user: str, password: str) -> bool:
    """Whether ``user`` gets a token from realm mock-idp with ``password`` (kcadm, admin-cli)."""
    result = _docker(
        "run", "--rm", "--network", network, "-e", f"KC_CLI_PASSWORD={password}",
        "--entrypoint", KCADM, image, "config", "credentials", "--config", "/tmp/kcadm.config",
        "--server", server, "--realm", "mock-idp", "--user", user,
        check=False, timeout=120,
    )  # fmt: skip
    return result.returncode == 0


def _run_users_script(image: str, network: str, server: str) -> subprocess.CompletedProcess[str]:
    # As compose runs it: read-only root, tmpfs /tmp, no capabilities, UID 1000.
    return _docker(
        "run", "--rm", "--network", network, "--user", "1000", "--read-only",
        "--tmpfs", "/tmp:size=64m,mode=1777", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "-e", f"KEYCLOAK_SERVER={server}", "-e", "KEYCLOAK_ADMIN=admin",
        "-e", f"KEYCLOAK_ADMIN_PASSWORD={ADMIN_PASSWORD}",
        "-e", f"MOCK_IDP_ALICE_PASSWORD={ALICE_PASSWORD}",
        "-e", "MOCK_IDP_BOB_PASSWORD=Bob-from-the-secret-store-1",
        "--entrypoint", "/opt/keycloak/aip/mock-idp-users.sh", image,
        check=False, timeout=300,
    )  # fmt: skip


def test_alice_signs_in_with_the_secret_password_not_the_committed_one(
    image: str, keycloak: tuple[str, str]
) -> None:
    name, network = keycloak
    server = f"http://{name}:8080/auth"
    # The deployed realm imports no users.
    assert not _sign_in(image, network, server, "alice@kaefer.test", "alice_dev_only_password")

    result = _run_users_script(image, network, server)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "created alice@kaefer.test" in result.stdout
    assert ALICE_PASSWORD not in result.stdout + result.stderr

    assert _sign_in(image, network, server, "alice@kaefer.test", ALICE_PASSWORD)
    assert not _sign_in(image, network, server, "alice@kaefer.test", "alice_dev_only_password")

    # Idempotent: a redeploy keeps the user and sets the password again.
    again = _run_users_script(image, network, server)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "created" not in again.stdout
    assert _sign_in(image, network, server, "alice@kaefer.test", ALICE_PASSWORD)


def test_the_users_script_refuses_the_committed_dev_password(
    image: str, keycloak: tuple[str, str]
) -> None:
    _, network = keycloak
    result = _docker(
        "run", "--rm", "--network", network,
        "-e", "KEYCLOAK_ADMIN_PASSWORD=x", "-e", "MOCK_IDP_ALICE_PASSWORD=alice_dev_only_password",
        "-e", "MOCK_IDP_BOB_PASSWORD=Bob-from-the-secret-store-1",
        "--entrypoint", "/opt/keycloak/aip/mock-idp-users.sh", image,
        check=False, timeout=120,
    )  # fmt: skip
    assert result.returncode == 1
    assert "public dev value" in result.stderr
