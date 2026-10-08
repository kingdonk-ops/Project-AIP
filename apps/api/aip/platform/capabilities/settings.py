"""Capability settings, read only from environment variables (STACK-02).

Variable names are the field names in upper case, for example ``OBJECT_STORE=s3`` or
``GOTENBERG_URL=http://gotenberg:3000``. Credentials are ``SecretStr`` so they never appear in
reprs or logs. Secrets are never read from the database: stored non-secret adapter config goes
through :func:`parse_adapter_config`.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aip.platform.capabilities.errors import SecretInConfigError

DEFAULT_RENDER_TIMEOUT_S = 30.0
DEFAULT_RENDER_MAX_BYTES = 25 * 1024 * 1024


class CapabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # Adapter selection. Unknown values are rejected by the factory (UnknownAdapterError).
    object_store: str = "minio"
    pdf_renderer: str = "gotenberg"

    # ObjectStore (both adapters).
    object_store_bucket: str = "aip"
    object_store_endpoint_url: str | None = None
    object_store_region: str = "ap-southeast-2"
    object_store_access_key_id: SecretStr | None = None
    object_store_secret_access_key: SecretStr | None = None
    # s3 adapter only; the minio adapter always uses path-style.
    object_store_addressing_style: Literal["auto", "virtual", "path"] = "auto"

    # PdfRenderer: Gotenberg.
    gotenberg_url: str = "http://localhost:3000"
    gotenberg_timeout_s: float = Field(default=DEFAULT_RENDER_TIMEOUT_S, gt=0)
    gotenberg_max_bytes: int = Field(default=DEFAULT_RENDER_MAX_BYTES, gt=0)

    @field_validator("object_store", "pdf_renderer")
    @classmethod
    def _normalise_adapter_key(cls, value: str) -> str:
        return value.strip().lower()


# Matched against lower-cased keys with "-" and spaces folded to "_", and against the same key
# with separators removed (so "accessKey" and "Access-Key" are caught).
_SECRET_KEY = re.compile(
    r"secret|password|passwd|token|access_?key|private_?key|credential|api_?key"
)


def _is_secret_like(key: str) -> bool:
    folded = re.sub(r"[-\s]", "_", key.lower())
    return bool(_SECRET_KEY.search(folded) or _SECRET_KEY.search(folded.replace("_", "")))


def _check(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for k, v in value.items():  # pyright: ignore[reportUnknownVariableType]
            child = f"{path}.{k}" if path else str(k)  # pyright: ignore[reportUnknownArgumentType]
            if _is_secret_like(str(k)):  # pyright: ignore[reportUnknownArgumentType]
                raise SecretInConfigError(child)
            _check(v, child)
    elif isinstance(value, list | tuple):
        for i, item in enumerate(value):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            _check(item, f"{path}[{i}]")


def parse_adapter_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate non-secret adapter config (e.g. from ``capability_adapter_settings``).

    Raises ``SecretInConfigError`` if any key, at any depth, looks like a secret
    (``secret|password|token|access_key`` and close variants). Returns a deep copy.
    """
    _check(config, "")
    return copy.deepcopy(dict(config))
