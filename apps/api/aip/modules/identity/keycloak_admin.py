"""Keycloak admin REST calls the backend makes (IDENTITY-03; part of STACK-02 ``IdentityProvider``).

Plain ``httpx`` against the admin REST API with the ``aip-admin`` service-account client
(client credentials; secret in ``KEYCLOAK_ADMIN_CLIENT_SECRET``). This drops ``python-keycloak``
and its LGPL ``jwcrypto`` from the runtime path (IDENTITY-01 carry-forward).

- ``revoke_kc_session(kc_sid)``: ``DELETE /admin/realms/{realm}/sessions/{kc_sid}``.
- ``logout_user(keycloak_user_id)``: ``POST /admin/realms/{realm}/users/{id}/logout``.
- ``end_sessions(user_id)``: the ``IdentityProvider`` name for ``logout_user``.

Both are idempotent: 404 counts as success. Other errors raise ``KeycloakAdminError`` so the job
retries. IDENTITY-04 and IDENTITY-05 add more methods (create, disable, IdP lookup).
"""

from __future__ import annotations

import time
from typing import Final
from urllib.parse import quote

import httpx
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["KeycloakAdmin", "KeycloakAdminError", "KeycloakAdminSettings"]

_TOKEN_SKEW_S: Final = 30.0


class KeycloakAdminSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    keycloak_url: str = Field(default="http://localhost:8180", validation_alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="aip", validation_alias="KEYCLOAK_REALM")
    client_id: str = Field(default="aip-admin", validation_alias="KEYCLOAK_ADMIN_CLIENT_ID")
    client_secret: SecretStr = Field(validation_alias="KEYCLOAK_ADMIN_CLIENT_SECRET")
    timeout_seconds: float = Field(default=10.0, validation_alias="OIDC_HTTP_TIMEOUT_SECONDS")


class KeycloakAdminError(Exception):
    pass


class KeycloakAdmin:
    def __init__(self, settings: KeycloakAdminSettings, http: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self._token: str | None = None
        self._token_expires = 0.0
        base = settings.keycloak_url.rstrip("/")
        realm = quote(settings.keycloak_realm, safe="")
        self._token_url = f"{base}/realms/{realm}/protocol/openid-connect/token"
        self._admin = f"{base}/admin/realms/{realm}"

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _access_token(self) -> str:
        if self._token is not None and time.monotonic() < self._token_expires:
            return self._token
        response = await self._http.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.client_id,
                "client_secret": self._settings.client_secret.get_secret_value(),
            },
        )
        if response.status_code != 200:
            raise KeycloakAdminError(f"admin token request failed ({response.status_code})")
        body = response.json()
        self._token = str(body["access_token"])
        self._token_expires = time.monotonic() + float(body.get("expires_in", 60)) - _TOKEN_SKEW_S
        return self._token

    async def _call(self, method: str, path: str) -> None:
        for attempt in (1, 2):
            token = await self._access_token()
            response = await self._http.request(
                method, f"{self._admin}{path}", headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 401 and attempt == 1:
                self._token = None  # the cached token was revoked or expired early: retry once
                continue
            if response.status_code in (200, 204, 404):
                return
            raise KeycloakAdminError(
                f"{method} {path.split('/')[1]} failed ({response.status_code})"
            )

    async def revoke_kc_session(self, kc_sid: str) -> None:
        await self._call("DELETE", f"/sessions/{quote(kc_sid, safe='')}")

    async def logout_user(self, keycloak_user_id: str) -> None:
        await self._call("POST", f"/users/{quote(keycloak_user_id, safe='')}/logout")

    async def end_sessions(self, user_id: str) -> None:
        await self.logout_user(user_id)
