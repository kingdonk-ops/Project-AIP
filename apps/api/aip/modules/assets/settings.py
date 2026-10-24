"""Assets settings (ASSETS-01), read from the environment.

``ASSETS_CURSOR_KEY`` signs list cursors. The dev default is obviously fake and refused in every
environment except development and test (so staging cannot run on a public key); deployed
environments take the value from their secret store. ``routes.py`` loads the settings when the app
starts, so a missing key fails the deploy instead of the first paged request (mirrors
``aip.modules.projects.settings``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_CURSOR_KEY = "dev-only-assets-cursor-key-not-secret"
# Where the dev key is allowed; "" is an unset AIP_ENV (local runs and the test suite).
DEV_KEY_ENVS = frozenset({"", "development", "test"})


class AssetsSettingsError(ValueError):
    """Assets settings are missing or invalid."""


class AssetsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    aip_env: str = Field(default="", validation_alias="AIP_ENV")
    cursor_key: SecretStr = Field(
        default=SecretStr(DEV_CURSOR_KEY), validation_alias="ASSETS_CURSOR_KEY", min_length=16
    )

    @model_validator(mode="after")
    def _no_dev_key_outside_dev(self) -> AssetsSettings:
        dev_key = self.cursor_key.get_secret_value() == DEV_CURSOR_KEY
        if dev_key and self.aip_env not in DEV_KEY_ENVS:
            raise AssetsSettingsError(f"ASSETS_CURSOR_KEY must be set when AIP_ENV={self.aip_env}")
        return self


@lru_cache(maxsize=1)
def get_settings() -> AssetsSettings:
    return AssetsSettings()
