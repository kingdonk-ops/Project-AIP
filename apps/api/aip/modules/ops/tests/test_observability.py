"""OPS-04: health endpoints, structured JSON logs with request/tenant ids, PII scrubber, tracing."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import structlog
from fastapi import FastAPI
from tests.conftest import (
    ALICE_ID,
    TENANT_A_ID,
    FixtureMembershipResolver,
    FixturePrincipalResolver,
)

from aip.main import create_app
from aip.modules.ops.health import ReadinessChecker
from aip.platform.context import Principal
from aip.platform.observability.logging import configure_logging
from aip.platform.observability.scrub import REDACTED, scrub

if TYPE_CHECKING:  # fixtures come from conftest.py; these imports are for type hints only
    from tests.platform.db.conftest import FreshDb

    from aip.modules.ops.tests.conftest import RedisServer

LIVE = "/api/v1/health/live"
READY = "/api/v1/health/ready"


def make_app(readiness: ReadinessChecker | None = None, **kwargs: Any) -> FastAPI:
    resolver = FixturePrincipalResolver(
        {"token-alice": Principal(tenant_id=TENANT_A_ID, actor_id=ALICE_ID)}
    )
    return create_app(
        principal_resolver=resolver,
        membership_resolver=FixtureMembershipResolver(),
        readiness=readiness,
        **kwargs,
    )


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def json_lines(out: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for raw in out.splitlines():
        raw = raw.strip()
        if raw.startswith("{"):
            lines.append(json.loads(raw))
    return lines


# --- unit: scrubber ---------------------------------------------------------------------------


def test_scrub_redacts_email_and_token_query_pair() -> None:
    out = scrub("user a@b.com token=abc")
    assert isinstance(out, str)
    assert "a@b.com" not in out
    assert "abc" not in out


def test_scrub_masks_sensitive_keys_recursively_and_case_insensitively() -> None:
    out = scrub({"pin": "1234", "nested": {"Password": "x"}, "keep": "fine"})
    assert out == {"pin": REDACTED, "nested": {"Password": REDACTED}, "keep": "fine"}


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("Authorization: Bearer eyJhbGciOi.payload.sig", "eyJhbGciOi.payload.sig"),
        ("GET /x?a=1&password=hunter2&b=2", "hunter2"),
        ("callback?access_token=s3cr3t", "s3cr3t"),
        ("contact Alice.Smith+tag@kaefer.test now", "Alice.Smith+tag@kaefer.test"),
    ],
)
def test_scrub_strings(raw: str, secret: str) -> None:
    out = scrub(raw)
    assert isinstance(out, str)
    assert secret not in out


def test_scrub_walks_lists_and_tuples_and_keeps_scalars() -> None:
    out = scrub(
        {
            "Authorization": "Bearer x",
            "SECRET": "y",
            "token": "z",
            "items": ["bob@acme.test", ("ok", 3)],
            "n": 7,
            "flag": True,
            "none": None,
        }
    )
    assert out == {
        "Authorization": REDACTED,
        "SECRET": REDACTED,
        "token": REDACTED,
        "items": ["[email]", ["ok", 3]],
        "n": 7,
        "flag": True,
        "none": None,
    }


# --- integration: logging ---------------------------------------------------------------------


async def test_request_log_line_carries_request_id_and_tenant_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = make_app()
    capsys.readouterr()
    async with client(app) as c:
        r = await c.get(LIVE, headers={"Authorization": "Bearer token-alice"})
    assert r.status_code == 200
    request_id = r.headers["x-request-id"]
    # Generated ids are UUIDv7.
    assert uuid.UUID(request_id).version == 7

    lines = [ln for ln in json_lines(capsys.readouterr().out) if ln.get("event") == "request"]
    assert len(lines) == 1
    line = lines[0]
    assert line["request_id"] == request_id
    assert line["tenant_id"] == str(TENANT_A_ID)
    assert line["status"] == 200
    assert line["path"] == LIVE
    assert line["level"] == "info"


async def test_given_request_id_is_echoed_and_logged(capsys: pytest.CaptureFixture[str]) -> None:
    app = make_app()
    capsys.readouterr()
    async with client(app) as c:
        r = await c.get(LIVE, headers={"X-Request-ID": "rid-ops-04"})
        unsafe = await c.get(LIVE, headers={"X-Request-ID": "bad id\nforged"})
    assert r.headers["x-request-id"] == "rid-ops-04"
    assert unsafe.headers["x-request-id"] != "bad id\nforged"
    lines = [ln for ln in json_lines(capsys.readouterr().out) if ln.get("event") == "request"]
    assert [ln["request_id"] for ln in lines] == ["rid-ops-04", unsafe.headers["x-request-id"]]
    # Unauthenticated: no tenant.
    assert "tenant_id" not in lines[0]


async def test_logs_inside_a_request_carry_request_id_and_stdlib_is_routed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = make_app()

    @app.get("/api/v1/_ops_test/log")
    async def log_something() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        structlog.get_logger("aip.test").info(
            "structlog line", email="carol@kaefer.test", password="hunter2"
        )
        logging.getLogger("aip.test.stdlib").warning(
            "stdlib line for %s with Bearer abc.def", "dave@acme.test"
        )
        return {"ok": "yes"}

    capsys.readouterr()
    async with client(app) as c:
        r = await c.get(
            "/api/v1/_ops_test/log?token=t0ps3cret", headers={"Authorization": "Bearer token-alice"}
        )
    assert r.status_code == 200
    out = capsys.readouterr().out
    for raw in ("carol@kaefer.test", "dave@acme.test", "hunter2", "abc.def", "t0ps3cret"):
        assert raw not in out
    lines = json_lines(out)
    structlog_line = next(ln for ln in lines if ln["event"] == "structlog line")
    stdlib_line = next(ln for ln in lines if ln["event"].startswith("stdlib line for "))
    for line in (structlog_line, stdlib_line):
        assert line["request_id"] == r.headers["x-request-id"]
        assert line["tenant_id"] == str(TENANT_A_ID)
    assert structlog_line["password"] == REDACTED
    assert stdlib_line["level"] == "warning"
    assert stdlib_line["logger"] == "aip.test.stdlib"


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    configure_logging()
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_aip_handler", False)]
    assert len(ours) == 1


# --- integration: health ----------------------------------------------------------------------


async def test_live_is_ok_without_touching_dependencies() -> None:
    checker = ReadinessChecker(database_url=None, redis_url=None)
    async with client(make_app(checker)) as c:
        live = await c.get(LIVE)
        legacy = await c.get("/api/v1/health")
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert legacy.json() == {"status": "ok"}


async def test_ready_fails_closed_when_unconfigured() -> None:
    checker = ReadinessChecker(database_url=None, redis_url=None)
    async with client(make_app(checker)) as c:
        r = await c.get(READY)
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "fail"
    assert set(body["checks"]) == {"db", "redis", "migrations"}
    assert all(v.startswith("fail") for v in body["checks"].values())


async def test_ready_ok_then_503_when_redis_stops(
    migrated_db: FreshDb, redis_server: RedisServer
) -> None:
    checker = ReadinessChecker(database_url=migrated_db.owner_url, redis_url=redis_server.url)
    app = make_app(checker)
    async with client(app) as c:
        ok = await c.get(READY)
        assert ok.status_code == 200, ok.text
        assert ok.json() == {
            "status": "ok",
            "checks": {"db": "ok", "redis": "ok", "migrations": "ok"},
        }

        redis_server.stop()
        down = await c.get(READY)
        live = await c.get(LIVE)
    assert down.status_code == 503
    body = down.json()
    assert body["status"] == "fail"
    assert body["checks"]["redis"].startswith("fail")
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["migrations"] == "ok"
    assert live.status_code == 200


async def test_ready_503_when_database_is_behind_head(
    migrated_db: FreshDb, redis_server: RedisServer, migrations_copy: Path
) -> None:
    from aip.platform.db.migrator import new

    # The database is at the committed head; the code (this copy) has one more revision.
    new.create_revision(
        "ops_04_ahead", config_path=migrations_copy, now=datetime(2099, 1, 1, 0, 0, tzinfo=UTC)
    )
    checker = ReadinessChecker(
        database_url=migrated_db.owner_url,
        redis_url=redis_server.url,
        alembic_config=migrations_copy,
    )
    async with client(make_app(checker)) as c:
        r = await c.get(READY)
    assert r.status_code == 503
    checks = r.json()["checks"]
    assert checks["migrations"].startswith("fail")
    assert "209901010000" in checks["migrations"]
    assert checks["db"] == "ok"
    assert checks["redis"] == "ok"


async def test_ready_503_when_database_is_unmigrated(
    bootstrapped_db: FreshDb, redis_server: RedisServer
) -> None:
    checker = ReadinessChecker(database_url=bootstrapped_db.owner_url, redis_url=redis_server.url)
    async with client(make_app(checker)) as c:
        r = await c.get(READY)
    assert r.status_code == 503
    assert r.json()["checks"]["migrations"].startswith("fail")
    assert r.json()["checks"]["db"] == "ok"


async def test_ready_check_times_out(migrated_db: FreshDb) -> None:
    # A listening socket that never answers: the Redis check must give up after its timeout.
    import socket

    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen()
        port = silent.getsockname()[1]
        checker = ReadinessChecker(
            database_url=migrated_db.owner_url,
            redis_url=f"redis://127.0.0.1:{port}/0",
            timeout=0.5,
        )
        async with client(make_app(checker)) as c:
            r = await c.get(READY)
    assert r.status_code == 503
    assert r.json()["checks"]["redis"] == "fail: timeout"


# --- tracing ----------------------------------------------------------------------------------


def test_tracing_is_a_no_op_without_endpoint() -> None:
    from aip.platform.observability.otel import init_tracing

    app = FastAPI()
    assert init_tracing(app, environ={}) is None
    assert not getattr(app, "_is_instrumented_by_opentelemetry", False)


async def test_tracing_exports_request_spans_when_endpoint_is_set() -> None:
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from aip.platform.observability.otel import init_tracing

    exporter = InMemorySpanExporter()
    app = make_app(tracing=False)

    @app.get("/api/v1/_ops_test/traced")
    async def traced() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": "yes"}

    handle = init_tracing(
        app,
        environ={"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318"},
        span_exporter=exporter,
        set_global=False,
    )
    assert handle is not None
    try:
        async with client(app) as c:
            r = await c.get("/api/v1/_ops_test/traced")
            await c.get(LIVE)  # health probes are not traced
        assert r.status_code == 200
        names = [s.name for s in exporter.get_finished_spans()]
        assert any("/api/v1/_ops_test/traced" in n for n in names)
        assert not any("/health" in n for n in names)
    finally:
        handle.shutdown()
