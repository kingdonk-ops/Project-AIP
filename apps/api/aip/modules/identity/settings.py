"""Identity settings (IDENTITY-01), read from the environment.

Two Keycloak base URLs, because the browser and the API reach Keycloak by different names in
compose (``localhost:8180`` from the host, ``keycloak:8080`` inside the network):

- ``KEYCLOAK_PUBLIC_URL``: what the browser sees; the authorize endpoint and the token issuer
  (Keycloak runs with ``KC_HOSTNAME`` set to it, so every token's ``iss`` uses it);
- ``KEYCLOAK_URL``: what the API calls server to server (token endpoint, JWKS).

IDENTITY-10: the client portal signs in through its own Keycloak client on its own host:
``PORTAL_ORIGIN`` (its callback is ``<PORTAL_ORIGIN>/api/v1/auth/portal/oidc/callback``),
``PORTAL_OIDC_CLIENT_ID`` (``aip-portal``) and ``PORTAL_OIDC_CLIENT_SECRET``. The secret is
optional so a deployment without the portal keeps staff sign-in; the portal routes then answer 503
``PORTAL_NOT_CONFIGURED``.

``OIDC_CLIENT_SECRET``, ``PORTAL_OIDC_CLIENT_SECRET`` and ``PREAUTH_COOKIE_KEY`` are secrets: dev
values are obviously fake and deployed environments take them from their secret store. The dev
values are refused unless ``AIP_ENV`` is development or test (an allowlist, SECURITY-11 Part D;
``aip.platform.dev_secrets`` also stops startup).
"""

from __future__ import annotations

import base64
import binascii
import os
from functools import cached_property

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aip.platform.dev_secrets import DEV_SECRET_ENVS, DEV_SECRETS

PREAUTH_KEY_BYTES = 32  # A256GCM
DEFAULT_PORTAL_ORIGIN = "http://portal.localhost:8081"
DEFAULT_PORTAL_CLIENT_ID = "aip-portal"
PORTAL_CALLBACK_PATH = "/api/v1/auth/portal/oidc/callback"


def portal_origin() -> str:
    """``PORTAL_ORIGIN`` from the environment (the CSRF middleware reads it at app start)."""
    return os.environ.get("PORTAL_ORIGIN", DEFAULT_PORTAL_ORIGIN).rstrip("/")


def portal_client_id() -> str:
    """``PORTAL_OIDC_CLIENT_ID`` from the environment (the invite job reads it in the worker)."""
    return os.environ.get("PORTAL_OIDC_CLIENT_ID", "").strip() or DEFAULT_PORTAL_CLIENT_ID


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
    portal_origin: str = Field(default=DEFAULT_PORTAL_ORIGIN, validation_alias="PORTAL_ORIGIN")
    portal_oidc_client_id: str = Field(
        default=DEFAULT_PORTAL_CLIENT_ID, validation_alias="PORTAL_OIDC_CLIENT_ID"
    )
    portal_oidc_client_secret: SecretStr | None = Field(
        default=None, validation_alias="PORTAL_OIDC_CLIENT_SECRET"
    )
    jwks_ttl_seconds: int = Field(default=300, validation_alias="OIDC_JWKS_TTL_SECONDS", ge=0)
    http_timeout_seconds: float = Field(default=10.0, validation_alias="OIDC_HTTP_TIMEOUT_SECONDS")

    @model_validator(mode="after")
    def _check(self) -> IdentitySettings:
        decode_preauth_key(self.preauth_cookie_key.get_secret_value())
        if self.aip_env in DEV_SECRET_ENVS:
            return self
        for name, secret in (
            ("OIDC_CLIENT_SECRET", self.oidc_client_secret),
            ("PORTAL_OIDC_CLIENT_SECRET", self.portal_oidc_client_secret),
            ("PREAUTH_COOKIE_KEY", self.preauth_cookie_key),
        ):
            if secret is not None and secret.get_secret_value() in DEV_SECRETS[name]:
                raise IdentitySettingsError(
                    f"the dev {name} must not be used with AIP_ENV={self.aip_env}"
                )
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

    @property
    def portal_redirect_uri(self) -> str:
        return f"{self.portal_origin.rstrip('/')}{PORTAL_CALLBACK_PATH}"

    @property
    def portal_configured(self) -> bool:
        secret = self.portal_oidc_client_secret
        return secret is not None and bool(secret.get_secret_value())
