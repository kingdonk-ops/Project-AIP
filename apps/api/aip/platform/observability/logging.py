"""Structured JSON logging and the request-id middleware (OPS-04).

``configure_logging()`` sends every log record, structlog's and the standard library's (uvicorn,
SQLAlchemy, Alembic, ...), through one structlog ``ProcessorFormatter`` that writes one JSON object
per line to stdout. Each line carries ``timestamp``, ``level``, ``logger`` and ``event``, plus
``request_id`` and, while a request context is set (ARCH-04), ``tenant_id``. The PII scrubber runs
last before rendering, so no line holds a raw email address, bearer token or secret value.

``RequestIdMiddleware`` is the outermost middleware. It is a pure ASGI middleware (not
``BaseHTTPMiddleware``, which would run the endpoint in another task and lose the ``ContextVar``):

1. read ``X-Request-ID`` when it is safe (``SAFE_REQUEST_ID``), otherwise generate a UUIDv7;
2. store it in the request-id ``ContextVar`` (``aip.platform.context``) and bind it to structlog's
   context variables for the request;
3. return it in the ``X-Request-ID`` response header;
4. log one ``request`` line (method, path without the query string, status, duration) when the
   response finishes. That line is written while the inner request-context middleware still has
   the tenant context set, so it carries ``tenant_id`` for authenticated requests;
5. on an unhandled exception, log ``unhandled exception`` with the traceback while the request id
   is still bound and, if no response has started, answer 500 ``{"detail": "Internal Server
   Error"}`` itself (with ``X-Request-ID``) instead of re-raising to Starlette's
   ``ServerErrorMiddleware``, which would build the 500 outside this middleware.

``uvicorn.access`` is silenced because the ``request`` line replaces it with a request id and
without the client address or query string. ``sqlalchemy.engine`` is pinned to ``WARNING`` and the
handler drops its records below ``WARNING``: its INFO/DEBUG lines (``echo=True``) contain SQL bound
parameters, which can hold any user data.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections.abc import MutableMapping
from typing import Any

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.typing import Processor

from aip.platform.context import ContextMissingError, get_context, reset_request_id, set_request_id
from aip.platform.context.middleware import REQUEST_ID_HEADER, request_id_from
from aip.platform.observability.scrub import scrub_processor

__all__ = [
    "LOG_LEVEL_ENV",
    "RequestIdMiddleware",
    "add_request_context",
    "configure_logging",
]

LOG_LEVEL_ENV = "AIP_LOG_LEVEL"
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")

_SQL_ENGINE_LOGGER = "sqlalchemy.engine"

access_logger = structlog.stdlib.get_logger("aip.access")
error_logger = structlog.stdlib.get_logger("aip.errors")


def add_request_context(
    logger: object, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: add ``request_id`` and ``tenant_id`` from the request context."""
    try:
        ctx = get_context()
    except ContextMissingError:
        return event_dict
    event_dict.setdefault("request_id", ctx.request_id)
    event_dict.setdefault("tenant_id", str(ctx.tenant_id))
    return event_dict


def _no_sql_parameters(record: logging.LogRecord) -> bool:
    """Drop ``sqlalchemy.engine`` records below WARNING (they carry bound parameters)."""
    name = record.name
    is_engine = name == _SQL_ENGINE_LOGGER or name.startswith(_SQL_ENGINE_LOGGER + ".")
    return not (is_engine and record.levelno < logging.WARNING)


class _StdoutHandler(logging.Handler):
    """Writes to whatever ``sys.stdout`` is at emit time (so pytest's ``capsys`` sees it)."""

    _aip_handler = True

    def __init__(self) -> None:
        super().__init__()
        self.addFilter(_no_sql_parameters)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stream = sys.stdout
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        add_request_context,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]


def configure_logging(level: str | int | None = None) -> None:
    """Route structlog and stdlib logging to JSON lines on stdout. Safe to call repeatedly.

    ``level`` defaults to ``AIP_LOG_LEVEL`` (``INFO``). Handlers other code added to the root
    logger (for example pytest's capture handler) are left in place.
    """
    if level is None:
        level = os.environ.get(LOG_LEVEL_ENV, "INFO").upper()

    shared = _shared_processors()
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            scrub_processor,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = _StdoutHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_aip_handler", False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn installs its own handlers before it loads the app: route them through the root.
    for name in _UVICORN_LOGGERS:
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Never log SQL bound parameters: SQLAlchemy emits them at INFO/DEBUG on this logger (and on
    # per-engine children when echo=True, which the handler filter above also drops).
    logging.getLogger(_SQL_ENGINE_LOGGER).setLevel(logging.WARNING)


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = request_id_from(Headers(scope=scope))
        started = time.perf_counter()
        status: int | None = None
        started_response = False
        logged = False

        def log_request(status_code: int) -> None:
            nonlocal logged
            if logged:
                return
            logged = True
            access_logger.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, started_response
            if message["type"] == "http.response.start":
                started_response = True
                status = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                log_request(status or 500)

        token = set_request_id(request_id)
        try:
            with structlog.contextvars.bound_contextvars(request_id=request_id):
                try:
                    await self.app(scope, receive, send_with_request_id)
                except Exception:
                    error_logger.exception(
                        "unhandled exception", method=scope.get("method"), path=scope.get("path")
                    )
                    if started_response:
                        # Too late for a 500: let the server abort the connection.
                        log_request(status or 500)
                        raise
                    response = JSONResponse({"detail": "Internal Server Error"}, status_code=500)
                    await response(scope, receive, send_with_request_id)
                except BaseException:
                    log_request(status or 500)
                    raise
                log_request(status or 500)
        finally:
            reset_request_id(token)
