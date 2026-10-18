"""SECURITY-11 Part B: the API caps request bodies and sends security headers on every response."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from aip.main import create_app
from aip.platform.http.edge import (
    MAX_BODY_BYTES,
    SECURITY_HEADERS,
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
)


class Payload(BaseModel):
    data: str


def _edge_app() -> FastAPI:
    app = FastAPI()

    @app.post("/json")
    async def json_body(payload: Payload) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"size": len(payload.data)}

    @app.post("/stream")
    async def stream_body(request: Request) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
        return {"size": size}

    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_edge_app()) as c:
        yield c


def _chunks(total: int, size: int = 64 * 1024) -> Iterator[bytes]:
    sent = 0
    while sent < total:
        part = min(size, total - sent)
        sent += part
        yield b"x" * part


@pytest.mark.parametrize("path", ["/json", "/stream"])
def test_a_body_over_the_cap_with_content_length_is_413(client: TestClient, path: str) -> None:
    response = client.post(
        path, content=b"x" * (MAX_BODY_BYTES + 1), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "request body too large"}


async def _send_chunked(app: Any, path: str, total: int) -> tuple[int, int]:
    """POST ``total`` bytes in 64 KiB chunks with no Content-Length, straight through ASGI.

    (The test client always sets Content-Length.) Returns the status and the bytes the app read.
    """
    chunks = list(_chunks(total))
    pulled = 0
    status = 0

    async def receive() -> dict[str, Any]:
        nonlocal pulled
        if pulled < len(chunks):
            pulled += 1
            more = pulled < len(chunks)
            return {"type": "http.request", "body": chunks[pulled - 1], "more_body": more}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json"), (b"transfer-encoding", b"chunked")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    return status, sum(len(c) for c in chunks[:pulled])


@pytest.mark.parametrize("path", ["/json", "/stream"])
async def test_a_chunked_body_over_the_cap_is_413(path: str) -> None:
    status, read = await _send_chunked(_edge_app(), path, MAX_BODY_BYTES + 1)
    assert status == 413
    assert read == MAX_BODY_BYTES + 1


async def test_a_2_mib_json_body_is_refused_without_being_buffered_whole() -> None:
    status, read = await _send_chunked(_edge_app(), "/json", 2 * MAX_BODY_BYTES)
    assert status == 413
    assert read <= MAX_BODY_BYTES + 64 * 1024  # stopped at the first chunk past the cap


async def test_a_chunked_body_at_the_cap_is_accepted() -> None:
    status, read = await _send_chunked(_edge_app(), "/stream", MAX_BODY_BYTES)
    assert (status, read) == (200, MAX_BODY_BYTES)


def test_a_body_at_the_cap_is_accepted(client: TestClient) -> None:
    data = "x" * (MAX_BODY_BYTES - len('{"data":""}'))
    response = client.post("/json", json={"data": data})
    assert response.status_code == 200
    assert response.json() == {"size": len(data)}
    assert client.post("/stream", content=_chunks(MAX_BODY_BYTES)).json() == {
        "size": MAX_BODY_BYTES
    }


def test_the_edge_responses_carry_the_security_headers(client: TestClient) -> None:
    for response in (
        client.post("/json", json={"data": "ok"}),
        client.post("/json", content=b"x" * (MAX_BODY_BYTES + 1)),
        client.get("/missing"),
    ):
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value, (response.status_code, name)


def test_every_api_response_carries_the_security_headers() -> None:
    client = TestClient(create_app(tracing=False))
    for response in (
        client.get("/api/v1/health"),
        client.get("/api/v1/does-not-exist"),
        client.post("/api/v1/health", content=b"x" * (MAX_BODY_BYTES + 1)),
    ):
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert response.headers["Strict-Transport-Security"].startswith("max-age=")


def test_the_api_refuses_an_oversized_body() -> None:
    client = TestClient(create_app(tracing=False))
    response = client.post("/api/v1/health", content=b"x" * (MAX_BODY_BYTES + 1))
    assert response.status_code == 413
    assert response.headers["x-request-id"]  # inside the request-id middleware, so it is logged
