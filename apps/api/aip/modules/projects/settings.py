"""Projects settings (PROJECTS-01), read from the environment.

``PROJECTS_CURSOR_KEY`` signs list cursors. The dev default is obviously fake and refused in
every environment except development and test (so staging cannot run on a public key); deployed
environments take the value from their secret store. ``routes.py`` loads the settings when the
app starts, so a missing key fails the deploy instead of the first paged request.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_CURSOR_KEY = "dev-only-projects-cursor-key-not-secret"
# Where the dev key is allowed; "" is an unset AIP_ENV (local runs and the test suite).
DEV_KEY_ENVS = frozenset({"", "development", "test"})


class ProjectsSettingsError(ValueError):
    """Projects settings are missing or invalid."""


class ProjectsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    aip_env: str = Field(default="", validation_alias="AIP_ENV")
    # Keep these arguments on separate lines: on one line, the gitleaks generic-api-key rule takes
    # the env var name and the length limit for a key and its value (see .gitleaksignore).
    cursor_key: SecretStr = Field(
        default=SecretStr(DEV_CURSOR_KEY),
        validation_alias="PROJECTS_CURSOR_KEY",
        min_length=16,
    )

    @model_validator(mode="after")
    def _no_dev_key_outside_dev(self) -> ProjectsSettings:
        dev_key = self.cursor_key.get_secret_value() == DEV_CURSOR_KEY
        if dev_key and self.aip_env not in DEV_KEY_ENVS:
            raise ProjectsSettingsError(
                f"PROJECTS_CURSOR_KEY must be set when AIP_ENV={self.aip_env}"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> ProjectsSettings:
    return ProjectsSettings()
