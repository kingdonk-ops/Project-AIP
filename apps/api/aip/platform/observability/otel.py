"""OpenTelemetry tracing (OPS-04): OTLP export of FastAPI, SQLAlchemy and Redis spans.

Tracing is on only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (the ADOT collector sidecar in
AWS, a local collector in compose); otherwise ``init_tracing`` does nothing and returns ``None``.
The exporter speaks OTLP over HTTP to ``<endpoint>/v1/traces`` unless
``OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`` names the full URL. ``OTEL_SERVICE_NAME`` defaults to
``aip-api``. Health probes are not traced.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import (  # pyright: ignore[reportMissingTypeStubs]
    SQLAlchemyInstrumentor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)

__all__ = ["ENDPOINT_ENV", "TracingHandle", "init_tracing"]

ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
TRACES_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
SERVICE_NAME_ENV = "OTEL_SERVICE_NAME"
DEFAULT_SERVICE_NAME = "aip-api"
EXCLUDED_URLS = "/api/v1/health"


@dataclass
class TracingHandle:
    """What ``init_tracing`` switched on; ``shutdown()`` flushes spans and undoes it."""

    app: FastAPI
    provider: TracerProvider

    def shutdown(self) -> None:
        FastAPIInstrumentor.uninstrument_app(self.app)
        SQLAlchemyInstrumentor().uninstrument()
        RedisInstrumentor().uninstrument()
        self.provider.shutdown()


def _traces_endpoint(env: Mapping[str, str], base: str) -> str:
    explicit = env.get(TRACES_ENDPOINT_ENV)
    if explicit:
        return explicit
    return base.rstrip("/") + "/v1/traces"


def init_tracing(
    app: FastAPI,
    *,
    environ: Mapping[str, str] | None = None,
    span_exporter: SpanExporter | None = None,
    set_global: bool = True,
) -> TracingHandle | None:
    """Instrument ``app``, SQLAlchemy and Redis when an OTLP endpoint is configured.

    ``span_exporter`` replaces the OTLP exporter (tests pass an in-memory one; spans are then
    exported synchronously). ``set_global=False`` leaves the global tracer provider alone.
    """
    env = os.environ if environ is None else environ
    endpoint = env.get(ENDPOINT_ENV, "").strip()
    if not endpoint:
        return None

    resource = Resource.create({"service.name": env.get(SERVICE_NAME_ENV) or DEFAULT_SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    if span_exporter is None:
        exporter = OTLPSpanExporter(endpoint=_traces_endpoint(env, endpoint))
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    if set_global:
        trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=EXCLUDED_URLS)
    SQLAlchemyInstrumentor().instrument(  # pyright: ignore[reportUnknownMemberType]
        tracer_provider=provider
    )
    RedisInstrumentor().instrument(  # pyright: ignore[reportUnknownMemberType]
        tracer_provider=provider
    )
    return TracingHandle(app=app, provider=provider)
