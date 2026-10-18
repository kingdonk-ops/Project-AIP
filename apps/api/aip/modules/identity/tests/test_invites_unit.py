"""IDENTITY-04 unit tests: invite method, step-up checks, upstream amr, the step-up URL, the
step-up callback checks and the Keycloak admin adapter (against an in-process mock)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
import pytest

from aip.modules.identity.invites import invite_method
from aip.modules.identity.keycloak_admin import (
    KeycloakAdmin,
    KeycloakAdminSettings,
    KeycloakRejected,
    KeycloakUnavailable,
)
from aip.modules.identity.oidc import OidcError
from aip.modules.identity.sessions import derive_aal
from aip.modules.identity.step_up import (
    StepUpRequiredError,
    build_step_up_url,
    check_step_up,
    check_step_up_callback,
    step_up_url,
)

NOW = datetime(2026, 10, 18, 10, 0, tzinfo=UTC)
DIRECTORY = {"kaefer.test": "kaefer-oidc"}


def test_invite_method() -> None:
    assert invite_method("carol@client.test", directory=DIRECTORY) == "local"
    assert invite_method("dan@kaefer.test", directory=DIRECTORY) == "sso"
    assert invite_method("Dan@KAEFER.test", directory=DIRECTORY) == "sso"


@pytest.mark.parametrize(
    ("aal", "minutes_ago", "ok"),
    [(2, 5, True), (2, 10, True), (2, 11, False), (1, 1, False)],
)
def test_check_step_up(aal: int, minutes_ago: int, ok: bool) -> None:
    at = NOW - timedelta(minutes=minutes_ago)
    assert check_step_up(aal=aal, authenticated_at=at, now=NOW, max_age_min=10) is ok


def test_check_step_up_without_an_authentication_time() -> None:
    assert check_step_up(aal=2, authenticated_at=None, now=NOW, max_age_min=10) is False


def test_step_up_required_body() -> None:
    exc = StepUpRequiredError("/settings/users?tab=invites")
    assert exc.status_code == 401
    detail = cast(dict[str, str], exc.detail)
    assert detail["code"] == "STEP_UP_REQUIRED"
    assert detail["stepUpUrl"] == step_up_url("/settings/users?tab=invites")
    assert detail["stepUpUrl"].startswith("/api/v1/auth/step-up/start?returnTo=/settings/users")
    # An off-site return address is never echoed into the step-up URL.
    assert step_up_url("https://evil.test/") == "/api/v1/auth/step-up/start?returnTo=/"


def test_derive_aal_counts_the_upstream_idp() -> None:
    assert derive_aal(acr=None, amr=["pwd"], upstream_amr=["pwd", "mfa"]) == 2
    assert derive_aal(None, [], upstream_amr=["pwd"]) == 1
    assert derive_aal("aal1", [], upstream_amr=["hwk"]) == 2
    assert derive_aal("aal2", ["pwd", "otp"]) == 2


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_build_step_up_url_for_an_sso_user() -> None:
    url = build_step_up_url(
        email="alice@kaefer.test",
        idp_alias="kaefer-oidc",
        authorize_endpoint="https://kc.test/realms/aip/protocol/openid-connect/auth",
        client_id="aip-api",
        redirect_uri="https://app.test/api/v1/auth/oidc/callback",
        state="s",
        nonce="n",
        code_verifier="v" * 64,
    )
    q = _query(url)
    assert q["prompt"] == "login"
    assert q["max_age"] == "0"
    assert q["acr_values"] == "aal2"
    assert q["kc_idp_hint"] == "kaefer-oidc"
    assert q["login_hint"] == "alice@kaefer.test"
    assert q["code_challenge_method"] == "S256"


def test_build_step_up_url_for_a_local_user_has_no_idp_hint() -> None:
    url = build_step_up_url(
        email="carol@client.test",
        idp_alias=None,
        authorize_endpoint="https://kc.test/auth",
        client_id="aip-api",
        redirect_uri="https://app.test/cb",
        state="s",
        nonce="n",
        code_verifier="v" * 64,
    )
    assert "kc_idp_hint" not in _query(url)


def test_step_up_callback_checks() -> None:
    sub = uuid4()
    started = NOW
    check_step_up_callback(
        expected_subject=sub, subject=str(sub), auth_time=started, started_at=started, aal=2
    )
    with pytest.raises(OidcError) as mismatch:
        check_step_up_callback(
            expected_subject=sub, subject=str(uuid4()), auth_time=started, started_at=started, aal=2
        )
    assert (mismatch.value.code, mismatch.value.status_code) == ("STEP_UP_SUBJECT_MISMATCH", 403)
    # A few seconds of clock skew between Keycloak and the API is tolerated, more is not.
    check_step_up_callback(
        expected_subject=sub,
        subject=str(sub),
        auth_time=started - timedelta(seconds=3),
        started_at=started,
        aal=2,
    )
    with pytest.raises(OidcError) as stale:
        check_step_up_callback(
            expected_subject=sub,
            subject=str(sub),
            auth_time=started - timedelta(seconds=6),
            started_at=started,
            aal=2,
        )
    assert stale.value.code == "STEP_UP_STALE"
    with pytest.raises(OidcError) as weak:
        check_step_up_callback(
            expected_subject=sub, subject=str(sub), auth_time=started, started_at=started, aal=1
        )
    assert weak.value.code == "MFA_NOT_SATISFIED"
    with pytest.raises(OidcError) as unlinked:
        check_step_up_callback(
            expected_subject=None, subject=str(sub), auth_time=started, started_at=started, aal=2
        )
    assert unlinked.value.code == "STEP_UP_SUBJECT_MISMATCH"


# --- Keycloak admin adapter ---------------------------------------------------------------------

KC = "https://kc.test"
EXISTING = UUID("00000000-0000-4000-8000-0000000000e1")


class FakeKeycloak:
    """The admin endpoints the adapter calls, in process."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, object]] = {}
        self.credentials: dict[str, list[dict[str, str]]] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail_with: int | None = None
        self.fail_message = "nope"
        self.emails: list[dict[str, object]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        if path.endswith("/protocol/openid-connect/token"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": 300})
        if self.fail_with is not None:
            return httpx.Response(self.fail_with, json={"errorMessage": self.fail_message})
        base = "/admin/realms/aip/users"
        if path == base and request.method == "POST":
            body = json.loads(request.content)
            for uid, user in self.users.items():
                if user["email"] == body["email"]:
                    del uid
                    return httpx.Response(409, json={"errorMessage": "User exists with same email"})
            uid = str(uuid4())
            self.users[uid] = {**body, "id": uid}
            return httpx.Response(201, headers={"location": f"{KC}{base}/{uid}"})
        if path == base and request.method == "GET":
            email = request.url.params["email"]
            return httpx.Response(200, json=[u for u in self.users.values() if u["email"] == email])
        uid = path.removeprefix(base + "/").split("/")[0]
        if uid not in self.users:
            return httpx.Response(404, json={"error": "User not found"})
        user = self.users[uid]
        if path.endswith("/execute-actions-email"):
            self.emails.append({"user": uid, **dict(request.url.params)})
            return httpx.Response(204)
        if path.endswith("/credentials") and request.method == "GET":
            return httpx.Response(200, json=self.credentials.get(uid, []))
        if "/credentials/" in path and request.method == "DELETE":
            cid = path.rsplit("/", 1)[-1]
            self.credentials[uid] = [c for c in self.credentials.get(uid, []) if c["id"] != cid]
            return httpx.Response(204)
        if request.method == "GET":
            return httpx.Response(200, json=user)
        if request.method == "PUT":
            user.update(json.loads(request.content))
            return httpx.Response(204)
        return httpx.Response(405)


@pytest.fixture
def kc() -> FakeKeycloak:
    return FakeKeycloak()


@pytest.fixture
async def admin(kc: FakeKeycloak):
    settings = KeycloakAdminSettings.model_validate(
        {"KEYCLOAK_URL": KC, "KEYCLOAK_ADMIN_CLIENT_SECRET": "test_only"}
    )
    client = KeycloakAdmin(
        settings, http=httpx.AsyncClient(transport=httpx.MockTransport(kc.handler))
    )
    yield client
    await client.aclose()


async def test_create_user_is_idempotent_on_email(admin: KeycloakAdmin, kc: FakeKeycloak) -> None:
    actions = ["VERIFY_EMAIL", "UPDATE_PASSWORD", "CONFIGURE_TOTP"]
    first = await admin.create_user(
        "carol@client.test",
        first_name="Carol",
        last_name="Client",
        required_actions=actions,
        attributes={"aip_user_id": ["u-1"]},
    )
    again = await admin.create_user(
        "carol@client.test", first_name="", last_name="", required_actions=[], attributes={}
    )
    assert first == again
    assert len(kc.users) == 1
    user = kc.users[str(first)]
    assert user["requiredActions"] == actions
    assert user["emailVerified"] is False
    assert user["attributes"] == {"aip_user_id": ["u-1"]}


async def test_send_actions_email_uses_the_client_base_url(
    admin: KeycloakAdmin, kc: FakeKeycloak
) -> None:
    uid = await admin.create_user(
        "carol@client.test", first_name="C", last_name="C", required_actions=[], attributes={}
    )
    await admin.send_actions_email(uid, ["VERIFY_EMAIL"], lifespan_s=604800)
    assert kc.emails == [{"user": str(uid), "client_id": "aip-api", "lifespan": "604800"}]


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (500, KeycloakUnavailable),
        (503, KeycloakUnavailable),
        (400, KeycloakRejected),
        (403, KeycloakRejected),
    ],
)
async def test_errors_are_unavailable_or_rejected(
    admin: KeycloakAdmin, kc: FakeKeycloak, status: int, error: type[Exception]
) -> None:
    kc.fail_with = status
    with pytest.raises(error):
        await admin.create_user(
            "x@client.test", first_name="", last_name="", required_actions=[], attributes={}
        )


async def test_a_rejection_carries_keycloaks_message(
    admin: KeycloakAdmin, kc: FakeKeycloak
) -> None:
    kc.fail_with = 400
    with pytest.raises(KeycloakRejected) as exc:
        await admin.disable_user(EXISTING)
    assert exc.value.message == "nope"


async def test_a_network_failure_is_unavailable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    settings = KeycloakAdminSettings.model_validate(
        {"KEYCLOAK_URL": KC, "KEYCLOAK_ADMIN_CLIENT_SECRET": "test_only"}
    )
    client = KeycloakAdmin(settings, http=httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    with pytest.raises(KeycloakUnavailable):
        await client.enable_user(EXISTING)
    await client.aclose()


async def test_disable_is_idempotent_for_a_missing_user(admin: KeycloakAdmin) -> None:
    await admin.disable_user(EXISTING)  # 404: already gone counts as disabled


async def test_reset_mfa_drops_second_factors_and_requires_totp(
    admin: KeycloakAdmin, kc: FakeKeycloak
) -> None:
    uid = await admin.create_user(
        "carol@client.test",
        first_name="C",
        last_name="C",
        required_actions=["VERIFY_EMAIL"],
        attributes={},
    )
    kc.credentials[str(uid)] = [
        {"id": "c-pwd", "type": "password"},
        {"id": "c-otp", "type": "otp"},
        {"id": "c-key", "type": "webauthn"},
        {"id": "c-pk", "type": "webauthn-passwordless"},
    ]
    await admin.reset_mfa(uid)
    assert [c["type"] for c in kc.credentials[str(uid)]] == ["password"]
    assert kc.users[str(uid)]["requiredActions"] == ["VERIFY_EMAIL", "CONFIGURE_TOTP"]
    await admin.reset_mfa(uid)  # a retried job changes nothing more
    assert kc.users[str(uid)]["requiredActions"] == ["VERIFY_EMAIL", "CONFIGURE_TOTP"]
