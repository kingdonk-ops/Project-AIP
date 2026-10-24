"""SECURITY-11 Part D: public dev secrets are refused unless AIP_ENV is development or test."""

from __future__ import annotations

import base64

import pytest

from aip.modules.identity.settings import IdentitySettings, IdentitySettingsError
from aip.platform.dev_secrets import (
    DEV_DATABASE_PASSWORDS,
    DEV_PREAUTH_COOKIE_KEY,
    DEV_SECRETS,
    DevSecretError,
    check_no_dev_secrets,
    dev_secrets_in,
)

DEPLOYED_ENVS = ["demo", "staging", "production", "prod", "Development"]
DEV_ENVS = ["", "development", "test"]
KNOWN = [(name, value) for name, values in DEV_SECRETS.items() for value in sorted(values)]
# A valid 32-byte key that is not a dev value, built here so no key-shaped literal is committed.
REAL_KEY = base64.urlsafe_b64encode(b"not-a-dev-key-but-a-test-key-32b").decode().rstrip("=")


@pytest.mark.parametrize("aip_env", DEPLOYED_ENVS)
@pytest.mark.parametrize(("name", "value"), KNOWN, ids=[n for n, _ in KNOWN])
def test_a_deployed_env_with_a_dev_secret_refuses_to_start(
    aip_env: str, name: str, value: str
) -> None:
    with pytest.raises(DevSecretError, match=f"AIP_ENV={aip_env} .*{name}"):
        check_no_dev_secrets({"AIP_ENV": aip_env, name: value})


@pytest.mark.parametrize("aip_env", DEPLOYED_ENVS)
@pytest.mark.parametrize("password", sorted(DEV_DATABASE_PASSWORDS))
def test_a_dev_database_password_in_any_url_refuses_to_start(aip_env: str, password: str) -> None:
    env = {"AIP_ENV": aip_env, "DATABASE_JOBS_URL": f"postgresql://u:{password}@db:5432/aip"}
    with pytest.raises(DevSecretError, match="DATABASE_JOBS_URL"):
        check_no_dev_secrets(env)


@pytest.mark.parametrize("aip_env", DEV_ENVS)
def test_dev_and_test_may_use_the_dev_secrets(aip_env: str) -> None:
    env = {"AIP_ENV": aip_env, **{name: value for name, value in KNOWN}}
    env["DATABASE_URL"] = "postgresql://aip_app:aip_app_dev_only@postgres:5432/aip"
    check_no_dev_secrets(env)


def test_deployed_envs_with_their_own_secrets_start() -> None:
    env = {
        "AIP_ENV": "demo",
        "OIDC_CLIENT_SECRET": "from-the-secret-store",
        "PREAUTH_COOKIE_KEY": REAL_KEY,
        "DATABASE_URL": "postgresql://aip_app:s3cret@postgres:5432/aip",
        "REDIS_URL": "redis://valkey:6379/0",
    }
    check_no_dev_secrets(env)
    assert dev_secrets_in(env) == []


def test_the_message_names_every_dev_secret_but_no_value() -> None:
    env = {
        "AIP_ENV": "demo",
        "OIDC_CLIENT_SECRET": "aip_api_dev_only_secret",
        "DATABASE_URL": "postgresql://aip_app:aip_app_dev_only@postgres:5432/aip",
    }
    with pytest.raises(DevSecretError) as caught:
        check_no_dev_secrets(env)
    assert "DATABASE_URL, OIDC_CLIENT_SECRET" in str(caught.value)
    assert "dev_only" not in str(caught.value)


@pytest.mark.parametrize("aip_env", DEPLOYED_ENVS)
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OIDC_CLIENT_SECRET", "aip_api_dev_only_secret"),
        ("PREAUTH_COOKIE_KEY", DEV_PREAUTH_COOKIE_KEY),
    ],
)
def test_identity_settings_refuse_dev_secrets_outside_dev(
    monkeypatch: pytest.MonkeyPatch, aip_env: str, name: str, value: str
) -> None:
    env = {"AIP_ENV": aip_env, "OIDC_CLIENT_SECRET": "real", "PREAUTH_COOKIE_KEY": REAL_KEY}
    env[name] = value
    for key, val in env.items():
        monkeypatch.setenv(key, val)
    with pytest.raises((IdentitySettingsError, ValueError), match=name):
        IdentitySettings()  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize("aip_env", DEV_ENVS)
def test_identity_settings_accept_dev_secrets_in_dev(
    monkeypatch: pytest.MonkeyPatch, aip_env: str
) -> None:
    monkeypatch.setenv("AIP_ENV", aip_env)
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "aip_api_dev_only_secret")
    monkeypatch.setenv("PREAUTH_COOKIE_KEY", DEV_PREAUTH_COOKIE_KEY)
    IdentitySettings()  # pyright: ignore[reportCallIssue]


def test_create_app_refuses_a_dev_secret_in_the_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    from aip.main import create_app

    monkeypatch.setenv("AIP_ENV", "demo")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "aip_api_dev_only_secret")
    with pytest.raises(DevSecretError):
        create_app(tracing=False)
