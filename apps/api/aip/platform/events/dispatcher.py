"""The outbox dispatcher: deliver ``domain_events`` to subscribers (ARCH-07, ADR 0003/0030).

``dispatch_batch`` claims up to ``batch_size`` due events as ``aip_jobs`` with
``FOR UPDATE SKIP LOCKED`` and holds those row locks until it has recorded every outcome, so two
dispatchers running at once never claim the same event. For each claimed event it runs every
subscriber in **one** ``aip_app`` transaction bound to the event's tenant (``use_context`` +
``with_tenant``): either all subscribers' effects commit and the event is published, or none do and
the event is retried after ``backoff(attempts)``; at ``max_attempts`` it is dead-lettered. A failing
event never stops the rest of the batch.

Delivery is at least once: a crash after a subscriber transaction committed but before the claim
transaction recorded ``published_at`` delivers the event again, which is why handlers must be
idempotent on ``event.id``.

``alert_dead_letter_thresholds`` runs after each drain: a tenant with more than
``dead_letter_alert_threshold`` live dead letters gets one
``platform.outbox.dead_letter_threshold_exceeded`` event in its own outbox per hour, and a
structured warning is logged.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import timedelta
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aip.platform.context import RequestContext, use_context
from aip.platform.db.session import with_tenant
from aip.platform.events.outbox import Aggregate, emit
from aip.platform.events.registry import PLATFORM_OUTBOX_THRESHOLD_EXCEEDED
from aip.platform.events.subscribers import DomainEvent, Subscriber, SubscriberRegistry

__all__ = [
    "LAST_ERROR_MAX",
    "BatchResult",
    "DispatchSettings",
    "Outcome",
    "alert_dead_letter_thresholds",
    "backoff",
    "dispatch_batch",
    "drain",
    "failure_outcome",
]

logger = structlog.stdlib.get_logger(__name__)

LAST_ERROR_MAX = 2000  # the column allows 4000; keep well inside it
_ALERT_EVERY = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class DispatchSettings:
    """Dispatcher settings (module README); ``from_env`` reads the ``OUTBOX_*`` variables."""

    batch_size: int = 100
    poll_interval_s: int = 2
    max_attempts: int = 10
    backoff_base_s: float = 2.0
    backoff_cap_s: float = 3600.0
    dead_letter_alert_threshold: int = 10
    max_batches_per_run: int = 50

    def __post_init__(self) -> None:
        if self.batch_size < 1 or self.max_attempts < 1 or self.max_batches_per_run < 1:
            raise ValueError("batch_size, max_attempts and max_batches_per_run must be >= 1")
        if not 1 <= self.poll_interval_s <= 59:
            raise ValueError("poll_interval_s must be between 1 and 59 seconds")
        if self.backoff_base_s <= 0 or self.backoff_cap_s < self.backoff_base_s:
            raise ValueError("backoff_base_s must be > 0 and backoff_cap_s >= backoff_base_s")
        if self.dead_letter_alert_threshold < 0:
            raise ValueError("dead_letter_alert_threshold must be >= 0")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        env = os.environ if environ is None else environ
        values: dict[str, Any] = {}
        for field in fields(cls):
            raw = env.get(f"OUTBOX_{field.name.upper()}")
            if raw:
                values[field.name] = float(raw) if field.type == "float" else int(raw)
        return cls(**values)


class Outcome(StrEnum):
    PUBLISHED = "published"
    RETRY = "retry"
    DEAD_LETTER = "dead_letter"


def backoff(attempts: int, base_s: float = 2.0, cap_s: float = 3600.0) -> timedelta:
    """Wait before the try after failed try number ``attempts`` (1-based): ``base * 2**(n-1)``."""
    if attempts < 1:
        raise ValueError("attempts is 1-based")
    return timedelta(seconds=min(base_s * 2 ** (attempts - 1), cap_s))


def failure_outcome(attempts: int, max_attempts: int) -> Outcome:
    """What a failure at try number ``attempts`` leads to: retry, or dead-letter at the limit."""
    return Outcome.DEAD_LETTER if attempts >= max_attempts else Outcome.RETRY


@dataclass(frozen=True, slots=True)
class BatchResult:
    claimed: int = 0
    published: int = 0
    retried: int = 0
    dead_lettered: int = 0

    def __add__(self, other: BatchResult) -> BatchResult:
        return BatchResult(
            self.claimed + other.claimed,
            self.published + other.published,
            self.retried + other.retried,
            self.dead_lettered + other.dead_lettered,
        )


class SubscriberFailedError(Exception):
    def __init__(self, sub: Subscriber, cause: Exception) -> None:
        self.subscriber = sub
        self.cause = cause
        super().__init__(f"{sub.name}: {type(cause).__name__}: {cause}")


_CLAIM = text("""
    SELECT id, tenant_id, project_id, asset_id, event_name, event_version, aggregate_type,
           aggregate_id, payload, actor_id, occurred_at, attempts
    FROM domain_events
    WHERE published_at IS NULL AND dead_lettered_at IS NULL AND discarded_at IS NULL
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
    ORDER BY occurred_at
    LIMIT :n
    FOR UPDATE SKIP LOCKED
""")
_PUBLISHED = text("UPDATE domain_events SET published_at = now() WHERE id = :id")
_FAILED = text("""
    UPDATE domain_events
       SET attempts = :attempts,
           last_error = :error,
           next_attempt_at = now() + make_interval(secs => :delay),
           dead_lettered_at = CASE WHEN :dead THEN now() END
     WHERE id = :id
""")


def _bounded(message: str) -> str:
    return message if len(message) <= LAST_ERROR_MAX else message[: LAST_ERROR_MAX - 1] + "…"


async def _deliver(app_engine: AsyncEngine, subs: list[Subscriber], event: DomainEvent) -> None:
    """Run every subscriber of ``event`` in one transaction bound to the event's tenant."""
    ctx = RequestContext(
        tenant_id=event.tenant_id,
        request_id=f"outbox-{event.id}",
        actor_id=event.actor_id,
        project_id=event.project_id,
    )
    async with use_context(ctx), with_tenant(ctx, engine=app_engine) as conn:
        for sub in subs:
            try:
                await sub.handler(conn, event)
            except Exception as exc:
                raise SubscriberFailedError(sub, exc) from exc


async def _record_failure(
    claim: AsyncConnection, event: DomainEvent, error: str, settings: DispatchSettings
) -> Outcome:
    attempts = event.attempts + 1
    outcome = failure_outcome(attempts, settings.max_attempts)
    delay = backoff(attempts, settings.backoff_base_s, settings.backoff_cap_s)
    await claim.execute(
        _FAILED,
        {
            "id": event.id,
            "attempts": attempts,
            "error": _bounded(error),
            "delay": delay.total_seconds(),
            "dead": outcome is Outcome.DEAD_LETTER,
        },
    )
    logger.warning(
        "outbox delivery failed",
        event_id=str(event.id),
        tenant_id=str(event.tenant_id),
        event_name=event.event_name,
        event_version=event.event_version,
        attempts=attempts,
        outcome=str(outcome),
    )
    return outcome


async def dispatch_batch(
    jobs_engine: AsyncEngine,
    app_engine: AsyncEngine,
    subscribers: SubscriberRegistry,
    settings: DispatchSettings | None = None,
) -> BatchResult:
    """Claim and deliver one batch; return what happened to it."""
    settings = settings or DispatchSettings()
    published = retried = dead = 0
    async with jobs_engine.begin() as claim:
        rows = (await claim.execute(_CLAIM, {"n": settings.batch_size})).mappings().all()
        for row in rows:
            event = DomainEvent(**row)
            subs = subscribers.for_event(event.event_name, event.event_version)
            try:
                if subs:
                    await _deliver(app_engine, subs, event)
            except Exception as exc:
                outcome = await _record_failure(claim, event, str(exc), settings)
                if outcome is Outcome.DEAD_LETTER:
                    dead += 1
                else:
                    retried += 1
                continue
            await claim.execute(_PUBLISHED, {"id": event.id})
            published += 1
    return BatchResult(len(rows), published, retried, dead)


_DEAD_LETTER_COUNTS = text("""
    SELECT tenant_id, count(*) AS n
    FROM domain_events
    WHERE dead_lettered_at IS NOT NULL AND discarded_at IS NULL
    GROUP BY tenant_id
    HAVING count(*) > :threshold
""")
_ALERT_LOCK = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")
_RECENT_ALERT = text("""
    SELECT 1 FROM domain_events
    WHERE event_name = :name AND occurred_at > now() - make_interval(secs => :window)
    LIMIT 1
""")


async def alert_dead_letter_thresholds(
    jobs_engine: AsyncEngine, app_engine: AsyncEngine, threshold: int
) -> list[UUID]:
    """Emit the threshold event for each tenant over ``threshold`` (at most hourly); return them."""
    async with jobs_engine.connect() as conn:
        over = (await conn.execute(_DEAD_LETTER_COUNTS, {"threshold": threshold})).all()
    alerted: list[UUID] = []
    for tenant_id, count in over:
        ctx = RequestContext(tenant_id=tenant_id, request_id=f"outbox-alert-{tenant_id}")
        async with use_context(ctx), with_tenant(ctx, engine=app_engine) as conn:
            # Serialise per tenant so two dispatchers cannot both emit within the hour.
            await conn.execute(_ALERT_LOCK, {"key": f"outbox-alert:{tenant_id}"})
            recent = await conn.execute(
                _RECENT_ALERT,
                {
                    "name": PLATFORM_OUTBOX_THRESHOLD_EXCEEDED,
                    "window": _ALERT_EVERY.total_seconds(),
                },
            )
            if recent.first() is not None:
                continue
            await emit(
                conn,
                PLATFORM_OUTBOX_THRESHOLD_EXCEEDED,
                1,
                Aggregate("tenant", tenant_id),
                {"count": int(count), "threshold": threshold},
            )
        logger.warning(
            "outbox dead-letter threshold exceeded",
            tenant_id=str(tenant_id),
            count=int(count),
            threshold=threshold,
        )
        alerted.append(tenant_id)
    return alerted


async def drain(
    jobs_engine: AsyncEngine,
    app_engine: AsyncEngine,
    subscribers: SubscriberRegistry,
    settings: DispatchSettings | None = None,
) -> BatchResult:
    """Dispatch batches until one comes back short (or ``max_batches_per_run``), then alert."""
    settings = settings or DispatchSettings()
    total = BatchResult()
    for _ in range(settings.max_batches_per_run):
        result = await dispatch_batch(jobs_engine, app_engine, subscribers, settings)
        total += result
        if result.claimed < settings.batch_size:
            break
    await alert_dead_letter_thresholds(
        jobs_engine, app_engine, settings.dead_letter_alert_threshold
    )
    return total
