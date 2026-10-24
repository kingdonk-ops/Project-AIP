"""Refuse public dev secrets outside development and test (SECURITY-11 Part D, review 11 M4).

The repository is public, so every dev value in ``.env.example``, ``infra/docker-compose.yml`` and
the Keycloak dev realms is known to anyone. :func:`check_no_dev_secrets` runs at API and worker
startup and refuses to start when any of them is configured and ``AIP_ENV`` is not in
:data:`DEV_SECRET_ENVS`: an allowlist, so a new environment name (``demo``, ``staging``, a typo) is
treated as deployed. ``""`` is an unset ``AIP_ENV`` (local runs and the test suite), as in
``aip.modules.projects.settings``; every deployed environment sets ``AIP_ENV``.

Database URLs are checked by their password, so a dev password in any ``DATABASE_*_URL`` fails too.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import unquote, urlsplit

__all__ = [
    "DEV_PREAUTH_COOKIE_KEY",
    "DEV_SECRETS",
    "DEV_SECRET_ENVS",
    "DevSecretError",
    "check_no_dev_secrets",
    "dev_secrets_in",
]

# Where the dev values are allowed; "" is an unset AIP_ENV.
DEV_SECRET_ENVS = frozenset({"", "development", "test"})

# The compose dev default (base64url of an obviously fake 32-byte string).
DEV_PREAUTH_COOKIE_KEY = (
    "ZGV2LW9ubHktcHJlYXV0aC1jb29raWUta2V5LWZha2U"  # dev-only-preauth-cookie-key-fake
)

# Every publicly known dev secret, by the variable that carries it.
DEV_SECRETS: Mapping[str, frozenset[str]] = {
    "OIDC_CLIENT_SECRET": frozenset({"aip_api_dev_only_secret"}),
    "KEYCLOAK_ADMIN_CLIENT_SECRET": frozenset({"aip_admin_dev_only_secret"}),
    "PREAUTH_COOKIE_KEY": frozenset({DEV_PREAUTH_COOKIE_KEY}),
    "PROJECTS_CURSOR_KEY": frozenset({"dev-only-projects-cursor-key-not-secret"}),
    "OBJECT_STORE_ACCESS_KEY_ID": frozenset({"rustfs_dev_only"}),
    "OBJECT_STORE_SECRET_ACCESS_KEY": frozenset({"rustfs_dev_only_secret"}),
}

# Dev database passwords, wherever a DATABASE_*_URL carries them.
DEV_DATABASE_PASSWORDS = frozenset(
    {
        "aip_owner_dev_only",
        "aip_app_dev_only",
        "aip_jobs_dev_only",
        "aip_audit_writer_dev_only",
        "postgres_dev_only",
        "keycloak_dev_only",
    }
)


class DevSecretError(RuntimeError):
    """A publicly known dev secret is configured outside development and test."""


def _url_password(url: str) -> str | None:
    try:
        password = urlsplit(url).password
    except ValueError:
        return None
    return unquote(password) if password else None


def dev_secrets_in(environ: Mapping[str, str]) -> list[str]:
    """The names of the variables in ``environ`` that hold a known dev secret, sorted."""
    found = {name for name, values in DEV_SECRETS.items() if environ.get(name, "") in values}
    for name, value in environ.items():
        is_db_url = name.startswith("DATABASE_") and name.endswith("URL")
        if is_db_url and _url_password(value) in DEV_DATABASE_PASSWORDS:
            found.add(name)
    return sorted(found)


def check_no_dev_secrets(environ: Mapping[str, str] | None = None) -> None:
    """Refuse to start with a known dev secret unless ``AIP_ENV`` is development or test."""
    env = os.environ if environ is None else environ
    aip_env = env.get("AIP_ENV", "")
    if aip_env in DEV_SECRET_ENVS:
        return
    found = dev_secrets_in(env)
    if found:
        raise DevSecretError(
            f"AIP_ENV={aip_env} must not use the public dev value of {', '.join(found)}: "
            "set them from the secret store"
        )
