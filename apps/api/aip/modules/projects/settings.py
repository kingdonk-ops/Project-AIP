"""Projects settings (PROJECTS-01), read from the environment.

``PROJECTS_CURSOR_KEY`` signs list cursors. The dev default is obviously fake and refused in
production, where the value comes from the secret store.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_CURSOR_KEY = "dev-only-projects-cursor-key-not-secret"


class ProjectsSettingsError(ValueError):
    """Projects settings are missing or invalid."""


class ProjectsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    aip_env: str = Field(default="", validation_alias="AIP_ENV")
    cursor_key: SecretStr = Field(
        default=SecretStr(DEV_CURSOR_KEY), validation_alias="PROJECTS_CURSOR_KEY", min_length=16
    )

    @model_validator(mode="after")
    def _no_dev_key_in_production(self) -> ProjectsSettings:
        if self.aip_env == "production" and self.cursor_key.get_secret_value() == DEV_CURSOR_KEY:
            raise ProjectsSettingsError("PROJECTS_CURSOR_KEY must be set in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> ProjectsSettings:
    return ProjectsSettings()
