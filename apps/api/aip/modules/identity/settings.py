"""Identity settings (IDENTITY-01), read from the environment.

Two Keycloak base URLs, because the browser and the API reach Keycloak by different names in
compose (``localhost:8180`` from the host, ``keycloak:8080`` inside the network):

- ``KEYCLOAK_PUBLIC_URL``: what the browser sees; the authorize endpoint and the token issuer
  (Keycloak runs with ``KC_HOSTNAME`` set to it, so every token's ``iss`` uses it);
- ``KEYCLOAK_URL``: what the API calls server to server (token endpoint, JWKS).

``OIDC_CLIENT_SECRET`` and ``PREAUTH_COOKIE_KEY`` are secrets: dev values are obviously fake and
deployed environments take them from their secret store.
"""

from __future__ import annotations

import base64
import binascii
from functools import cached_property

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PREAUTH_KEY_BYTES = 32  # A256GCM

# The compose dev default (base64url of an obviously fake 32-byte string). Refused in production.
DEV_PREAUTH_COOKIE_KEY = (
    "ZGV2LW9ubHktcHJlYXV0aC1jb29raWUta2V5LWZha2U"  # dev-only-preauth-cookie-key-fake
)


class IdentitySettingsError(ValueError):
    """Identity settings are missing or invalid."""


def decode_preauth_key(value: str) -> bytes:
    """``PREAUTH_COOKIE_KEY``: base64url (padding optional) of exactly 32 random bytes."""
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise IdentitySettingsError("PREAUTH_COOKIE_KEY is not base64url") from exc
    if len(raw) != PREAUTH_KEY_BYTES:
        raise IdentitySettingsError(f"PREAUTH_COOKIE_KEY must decode to {PREAUTH_KEY_BYTES} bytes")
    return raw


class IdentitySettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    aip_env: str = Field(default="", validation_alias="AIP_ENV")
    keycloak_url: str = Field(default="http://localhost:8180", validation_alias="KEYCLOAK_URL")
    keycloak_public_url: str | None = Field(default=None, validation_alias="KEYCLOAK_PUBLIC_URL")
    keycloak_realm: str = Field(default="aip", validation_alias="KEYCLOAK_REALM")
    oidc_client_id: str = Field(default="aip-api", validation_alias="OIDC_CLIENT_ID")
    oidc_client_secret: SecretStr = Field(validation_alias="OIDC_CLIENT_SECRET")
    app_origin: str = Field(default="http://localhost:8080", validation_alias="APP_ORIGIN")
    preauth_cookie_key: SecretStr = Field(validation_alias="PREAUTH_COOKIE_KEY")
    jwks_ttl_seconds: int = Field(default=300, validation_alias="OIDC_JWKS_TTL_SECONDS", ge=0)
    http_timeout_seconds: float = Field(default=10.0, validation_alias="OIDC_HTTP_TIMEOUT_SECONDS")

    @model_validator(mode="after")
    def _check(self) -> IdentitySettings:
        decode_preauth_key(self.preauth_cookie_key.get_secret_value())
        if (
            self.aip_env == "production"
            and self.preauth_cookie_key.get_secret_value() == DEV_PREAUTH_COOKIE_KEY
        ):
            raise IdentitySettingsError("the dev PREAUTH_COOKIE_KEY must not be used in production")
        return self

    @cached_property
    def preauth_key(self) -> bytes:
        return decode_preauth_key(self.preauth_cookie_key.get_secret_value())

    def _realm_url(self, base: str) -> str:
        return f"{base.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def issuer(self) -> str:
        return self._realm_url(self.keycloak_public_url or self.keycloak_url)

    @property
    def authorize_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def token_endpoint(self) -> str:
        return f"{self._realm_url(self.keycloak_url)}/protocol/openid-connect/token"

    @property
    def jwks_uri(self) -> str:
        return f"{self._realm_url(self.keycloak_url)}/protocol/openid-connect/certs"

    @property
    def redirect_uri(self) -> str:
        return f"{self.app_origin.rstrip('/')}/api/v1/auth/oidc/callback"
