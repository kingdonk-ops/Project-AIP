"""Keycloak admin REST calls the backend makes (IDENTITY-03; part of STACK-02 ``IdentityProvider``).

Plain ``httpx`` against the admin REST API with the ``aip-admin`` service-account client
(client credentials; secret in ``KEYCLOAK_ADMIN_CLIENT_SECRET``). This drops ``python-keycloak``
and its LGPL ``jwcrypto`` from the runtime path (IDENTITY-01 carry-forward).

- ``revoke_kc_session(kc_sid)``: ``DELETE /admin/realms/{realm}/sessions/{kc_sid}``.
- ``logout_user(keycloak_user_id)``: ``POST /admin/realms/{realm}/users/{id}/logout``.
- ``end_sessions(user_id)``: the ``IdentityProvider`` name for ``logout_user``.

Both are idempotent: 404 counts as success. Other errors raise ``KeycloakAdminError`` so the job
retries.

IDENTITY-04 adds the invite and MFA calls (``create_user``, ``send_actions_email``,
``enable_user``, ``disable_user``, ``reset_mfa``, ``get_user``). Their failures are
``KeycloakUnavailable`` (5xx, timeout, network, no admin token: retry later) or
``KeycloakRejected`` (4xx: Keycloak refused the request, with its message). Both are
``KeycloakAdminError``\\ s. Keycloak sends the invite email itself; no password, TOTP secret or
WebAuthn credential ever passes through here.
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "MFA_CREDENTIAL_TYPES",
    "KeycloakAdmin",
    "KeycloakAdminError",
    "KeycloakAdminSettings",
    "KeycloakRejected",
    "KeycloakUnavailable",
]

_TOKEN_SKEW_S: Final = 30.0
_MESSAGE_MAX: Final = 500
# The credential types an MFA reset removes (TOTP, security keys and passkeys).
MFA_CREDENTIAL_TYPES: Final = frozenset({"otp", "webauthn", "webauthn-passwordless"})


class KeycloakAdminSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    keycloak_url: str = Field(default="http://localhost:8180", validation_alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="aip", validation_alias="KEYCLOAK_REALM")
    client_id: str = Field(default="aip-admin", validation_alias="KEYCLOAK_ADMIN_CLIENT_ID")
    client_secret: SecretStr = Field(validation_alias="KEYCLOAK_ADMIN_CLIENT_SECRET")
    timeout_seconds: float = Field(default=10.0, validation_alias="OIDC_HTTP_TIMEOUT_SECONDS")


class KeycloakAdminError(Exception):
    pass


class KeycloakUnavailable(KeycloakAdminError):  # noqa: N818 - name fixed by the IDENTITY-04 spec
    """Keycloak could not be reached or failed (5xx, timeout): the caller should retry later."""


class KeycloakRejected(KeycloakAdminError):  # noqa: N818 - name fixed by the IDENTITY-04 spec
    """Keycloak refused the request (4xx); ``message`` is Keycloak's reason, safe to store."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _message(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        body = None
    if isinstance(body, Mapping):
        for key in ("errorMessage", "error_description", "error"):
            value: object = body.get(key)  # pyright: ignore[reportUnknownMemberType]
            if isinstance(value, str) and value:
                return value[:_MESSAGE_MAX]
    return f"Keycloak refused the request ({response.status_code})"


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
        try:
            response = await self._http.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._settings.client_id,
                    "client_secret": self._settings.client_secret.get_secret_value(),
                },
            )
        except httpx.HTTPError as exc:
            raise KeycloakUnavailable(f"admin token request failed ({type(exc).__name__})") from exc
        if response.status_code != 200:
            raise KeycloakUnavailable(f"admin token request failed ({response.status_code})")
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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: object = None,
        params: Mapping[str, str | int] | None = None,
    ) -> httpx.Response:
        """One admin call; 2xx returns the response, 4xx raises ``KeycloakRejected``."""
        for attempt in (1, 2):
            token = await self._access_token()
            try:
                response = await self._http.request(
                    method,
                    f"{self._admin}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    json=json,
                    params=params,
                )
            except httpx.HTTPError as exc:
                raise KeycloakUnavailable(
                    f"{method} {path.split('/')[1]} failed ({type(exc).__name__})"
                ) from exc
            if response.status_code == 401 and attempt == 1:
                self._token = None
                continue
            if response.is_success:
                return response
            if response.status_code >= 500 or response.status_code in (401, 429):
                raise KeycloakUnavailable(
                    f"{method} {path.split('/')[1]} failed ({response.status_code})"
                )
            raise KeycloakRejected(_message(response), response.status_code)
        raise AssertionError("unreachable")  # pragma: no cover

    # --- sessions (IDENTITY-03) ------------------------------------------------------------

    async def revoke_kc_session(self, kc_sid: str) -> None:
        await self._call("DELETE", f"/sessions/{quote(kc_sid, safe='')}")

    async def logout_user(self, keycloak_user_id: str) -> None:
        await self._call("POST", f"/users/{quote(keycloak_user_id, safe='')}/logout")

    async def end_sessions(self, user_id: str) -> None:
        await self.logout_user(user_id)

    # --- users (IDENTITY-04) ---------------------------------------------------------------

    @staticmethod
    def _user_path(user_id: UUID | str) -> str:
        return f"/users/{quote(str(user_id), safe='')}"

    async def find_user_by_email(self, email: str) -> UUID | None:
        response = await self._request(
            "GET", "/users", params={"email": email, "exact": "true", "briefRepresentation": "true"}
        )
        users: Any = response.json()
        for user in users if isinstance(users, list) else []:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(user, Mapping) and str(user.get("email", "")).lower() == email.lower():  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                return UUID(str(user["id"]))  # pyright: ignore[reportUnknownArgumentType]
        return None

    async def create_user(
        self,
        email: str,
        *,
        first_name: str,
        last_name: str,
        required_actions: Sequence[str],
        attributes: Mapping[str, Sequence[str]],
    ) -> UUID:
        """Create an enabled, unverified user with ``required_actions``; an existing email (409)
        returns that user's id, so a retried invite never creates a second account."""
        body = {
            "username": email,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": False,
            "requiredActions": list(required_actions),
            "attributes": {k: list(v) for k, v in attributes.items()},
        }
        try:
            response = await self._request("POST", "/users", json=body)
        except KeycloakRejected as exc:
            if exc.status_code != 409:
                raise
            existing = await self.find_user_by_email(email)
            if existing is None:
                raise
            return existing
        location = response.headers.get("location", "")
        user_id = location.rstrip("/").rsplit("/", 1)[-1]
        try:
            return UUID(user_id)
        except ValueError:
            found = await self.find_user_by_email(email)
            if found is None:
                raise KeycloakUnavailable("Keycloak created a user but returned no id") from None
            return found

    async def get_user(self, user_id: UUID | str) -> dict[str, Any]:
        response = await self._request("GET", self._user_path(user_id))
        return dict(response.json())

    async def send_actions_email(
        self,
        user_id: UUID | str,
        actions: Sequence[str],
        *,
        lifespan_s: int,
        redirect_uri: str | None = None,
        client_id: str = "aip-api",
    ) -> None:
        """Keycloak emails the user a link to complete ``actions`` (the ``aip`` email theme).

        Without ``redirect_uri`` the "back to the application" link is the client's base URL
        (``aip-api``: ``/login?invited=1``); a ``redirect_uri`` must be one of the client's
        registered redirect URIs, and ``aip-api`` registers only the API callback (review 11 L6).
        """
        params: dict[str, str | int] = {"client_id": client_id, "lifespan": lifespan_s}
        if redirect_uri is not None:
            params["redirect_uri"] = redirect_uri
        await self._request(
            "PUT",
            f"{self._user_path(user_id)}/execute-actions-email",
            json=list(actions),
            params=params,
        )

    async def _set_enabled(self, user_id: UUID | str, enabled: bool) -> None:
        await self._request("PUT", self._user_path(user_id), json={"enabled": enabled})

    async def enable_user(self, user_id: UUID | str) -> None:
        await self._set_enabled(user_id, True)

    async def disable_user(self, user_id: UUID | str) -> None:
        """Idempotent: a user Keycloak no longer has counts as disabled."""
        try:
            await self._set_enabled(user_id, False)
        except KeycloakRejected as exc:
            if exc.status_code != 404:
                raise

    async def credentials(self, user_id: UUID | str) -> list[dict[str, Any]]:
        response = await self._request("GET", f"{self._user_path(user_id)}/credentials")
        items: Any = response.json()
        return [dict(c) for c in items] if isinstance(items, list) else []  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]

    async def reset_mfa(
        self, user_id: UUID | str, *, types: Iterable[str] = MFA_CREDENTIAL_TYPES
    ) -> None:
        """Delete the user's OTP and WebAuthn credentials and require ``CONFIGURE_TOTP`` again."""
        wanted = set(types)
        for credential in await self.credentials(user_id):
            if credential.get("type") in wanted and credential.get("id"):
                try:
                    await self._request(
                        "DELETE",
                        f"{self._user_path(user_id)}/credentials/"
                        f"{quote(str(credential['id']), safe='')}",
                    )
                except KeycloakRejected as exc:
                    if exc.status_code != 404:  # already gone (a retried job)
                        raise
        user = await self.get_user(user_id)
        actions = [str(a) for a in user.get("requiredActions") or []]
        if "CONFIGURE_TOTP" not in actions:
            await self._request(
                "PUT",
                self._user_path(user_id),
                json={"requiredActions": [*actions, "CONFIGURE_TOTP"]},
            )
