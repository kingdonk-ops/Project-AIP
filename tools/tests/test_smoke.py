"""OPS-11: tools/smoke.py against a local stub server (no network, standard library)."""

from __future__ import annotations

import importlib.util
import sys
import threading
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("aip_smoke", ROOT / "tools" / "smoke.py")
assert _spec and _spec.loader
smoke: Any = importlib.util.module_from_spec(_spec)
sys.modules["aip_smoke"] = smoke
_spec.loader.exec_module(smoke)

PAGE = '<!doctype html><html><body><div role="note">Demo, synthetic data only</div></body></html>'


def serve(routes: dict[str, tuple[int, str]]) -> Generator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, body = routes.get(self.path, (404, "not found"))
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


HEALTHY = {
    "/api/v1/health/ready": (200, '{"status":"ok"}'),
    "/": (200, PAGE),
    "/api/v1/me": (401, '{"detail":{"code":"NOT_AUTHENTICATED"}}'),
}


@pytest.fixture
def healthy() -> Generator[str]:
    yield from serve(HEALTHY)


@pytest.fixture
def not_ready() -> Generator[str]:
    yield from serve(
        {**HEALTHY, "/api/v1/health/ready": (503, '{"status":"fail","checks":{"db":"fail"}}')}
    )


def test_a_healthy_stack_passes(healthy: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([healthy]) == 0
    assert "OK" in capsys.readouterr().out


def test_a_503_readiness_exits_1_with_a_readable_message(
    not_ready: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert smoke.main([not_ready]) == 1
    err = capsys.readouterr().err
    assert "readiness: GET /api/v1/health/ready answered 503, expected 200" in err
    assert '"db":"fail"' in err


def test_a_missing_banner_and_an_open_me_fail() -> None:
    gen = serve({**HEALTHY, "/": (200, "<html><body>app</body></html>"), "/api/v1/me": (200, "{}")})
    base = next(gen)
    try:
        failures = smoke.run(base)
    finally:
        gen.close()
    assert any("demo banner" in f for f in failures)
    assert any("anonymous /me" in f and "200" in f for f in failures)


def test_an_unreachable_host_and_a_bad_url_fail() -> None:
    assert smoke.run("ftp://example.test")
    failures = smoke.run("http://127.0.0.1:9", timeout=1)
    assert len(failures) == 3 and all("failed" in f for f in failures)


def test_expect_commit_checks_the_running_version() -> None:
    routes = {**HEALTHY, "/api/v1/platform/version": (200, '{"commit":"abc123"}')}
    gen = serve(routes)
    base = next(gen)
    try:
        assert smoke.run(base, expect_commit="abc123") == []
        assert any("expected 'def456'" in f for f in smoke.run(base, expect_commit="def456"))
    finally:
        gen.close()
