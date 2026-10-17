"""The client IP behind proxies (review 11 M1).

The login rate limit keys on ``request.client.host`` (and the session stores it), so that address
must be the real client's when a trusted proxy forwards the request, and must never come from a
header an untrusted peer sent. uvicorn's ``--proxy-headers`` does the rewriting; these tests load
the app through ``uvicorn.Config`` exactly as the image's ``CMD`` does and send requests from
chosen peer addresses.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from aip.modules.identity.routes import get_login_rate_limiter

ROOT = Path(__file__).resolve().parents[6]
DOCKERFILE = ROOT / "apps" / "api" / "Dockerfile"
LOGIN_START = "/api/v1/auth/login/start"
PRIVATE_HOPS = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


class RecordingLimiter:
    """Records the key of every ``login/start`` hit and refuses it (no sign-in work runs)."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def hit(self, client_key: str) -> bool:
        self.keys.append(client_key)
        return False


def _image_default_allow_ips() -> str:
    match = re.search(r'FORWARDED_ALLOW_IPS="([^"]*)"', DOCKERFILE.read_text(encoding="utf-8"))
    assert match, "apps/api/Dockerfile sets no FORWARDED_ALLOW_IPS default"
    return match.group(1)


@pytest.fixture
def limiter(app: FastAPI) -> RecordingLimiter:
    recorder = RecordingLimiter()
    app.dependency_overrides[get_login_rate_limiter] = lambda: recorder
    return recorder


async def _key_for(
    app: FastAPI,
    limiter: RecordingLimiter,
    monkeypatch: pytest.MonkeyPatch,
    *,
    allow_ips: str,
    peer: str,
    forwarded_for: str | None,
) -> str:
    """The rate-limit key for one request from ``peer`` through the image's uvicorn setup."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", allow_ips)
    # The CMD passes --proxy-headers; FORWARDED_ALLOW_IPS is read from the environment, as there.
    config = uvicorn.Config(app, proxy_headers=True, log_config=None)
    config.load()
    headers = {} if forwarded_for is None else {"X-Forwarded-For": forwarded_for}
    transport = httpx.ASGITransport(app=config.loaded_app, client=(peer, 50000))
    async with httpx.AsyncClient(transport=transport, base_url="https://app.example.test") as c:
        response = await c.post(LOGIN_START, json={"email": "x@kaefer.test"}, headers=headers)
    assert response.status_code == 429
    return limiter.keys[-1]


def test_the_image_passes_proxy_headers_and_trusts_loopback_only_by_default() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    cmd = next(line for line in text.splitlines() if line.startswith("CMD "))
    assert '"--proxy-headers"' in cmd
    assert "--forwarded-allow-ips" not in cmd  # the env var is the one knob
    assert _image_default_allow_ips() == "127.0.0.1,::1"


async def test_a_direct_client_cannot_pick_its_address_with_the_image_default(
    app: FastAPI, limiter: RecordingLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = await _key_for(
        app,
        limiter,
        monkeypatch,
        allow_ips=_image_default_allow_ips(),
        peer="203.0.113.7",
        forwarded_for="198.51.100.1",
    )
    assert key == "203.0.113.7"


async def test_a_trusted_proxy_hop_supplies_the_client_address(
    app: FastAPI, limiter: RecordingLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The ALB (in the VPC) or the web nginx forwards for the real client.
    key = await _key_for(
        app,
        limiter,
        monkeypatch,
        allow_ips=PRIVATE_HOPS,
        peer="10.0.4.20",
        forwarded_for="203.0.113.7",
    )
    assert key == "203.0.113.7"


async def test_a_spoofed_leftmost_entry_is_ignored(
    app: FastAPI, limiter: RecordingLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The client sent its own X-Forwarded-For; the proxy appended the real peer. The rightmost
    # untrusted address wins, so each attacker request still counts against its own address.
    keys = {
        await _key_for(
            app,
            limiter,
            monkeypatch,
            allow_ips=PRIVATE_HOPS,
            peer="10.0.4.20",
            forwarded_for=f"198.51.100.{n}, 203.0.113.7",
        )
        for n in range(3)
    }
    assert keys == {"203.0.113.7"}


async def test_an_untrusted_peer_keeps_its_own_address(
    app: FastAPI, limiter: RecordingLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = await _key_for(
        app,
        limiter,
        monkeypatch,
        allow_ips=PRIVATE_HOPS,
        peer="203.0.113.7",
        forwarded_for="198.51.100.1",
    )
    assert key == "203.0.113.7"


async def test_without_a_forwarded_header_the_peer_is_the_client(
    app: FastAPI, limiter: RecordingLimiter, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = await _key_for(
        app, limiter, monkeypatch, allow_ips=PRIVATE_HOPS, peer="10.0.4.20", forwarded_for=None
    )
    assert key == "10.0.4.20"
