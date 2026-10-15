"""The outbox dispatcher: deliver ``domain_events`` to subscribers (ARCH-07, ADR 0003/0030).

``dispatch_batch`` works in three short steps, so no transaction stays open while subscribers run:

1. **Claim** (``aip_jobs``, one transaction): select up to ``batch_size`` due events with
   ``FOR UPDATE SKIP LOCKED``, count the try (``attempts + 1``) and lease them
   (``next_attempt_at = now() + lease_s``), then commit. Two dispatchers never claim the same event,
   and an event whose dispatcher dies or hangs comes back when its lease runs out, with the try
   already counted, so a poison event still reaches the dead-letter queue. An event claimed again
   after ``max_attempts`` tries without an outcome is dead-lettered at claim.
2. **Deliver** (``aip_app``): every subscriber of the event in **one** transaction bound to the
   event's tenant (``use_context`` + ``with_tenant``): all subscribers' effects commit, or none do.
3. **Record** (``aip_jobs``, one transaction per event): ``published_at``, or ``last_error`` plus
   ``next_attempt_at = now() + backoff(attempts)``, dead-lettered at ``max_attempts``.

A failing event never stops the rest of the batch. Delivery is at least once (a crash between
steps 2 and 3, or a lease that runs out mid-delivery, delivers again), which is why handlers must
be idempotent on ``event.id``.

``last_error`` holds only the subscriber name, the exception type and a SQLSTATE: exception text
can carry tenant data (bound SQL parameters, validation inputs) and operators read dead letters
across tenants. The full text goes to the structured log.

``alert_dead_letter_thresholds`` runs at most every ``alert_interval_s`` from ``drain``: a tenant
with more than ``dead_letter_alert_threshold`` live dead letters gets one
``platform.outbox.dead_letter_threshold_exceeded`` event in its own outbox per hour, and a
structured warning is logged.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Self
from uuid import UUID

import structlog
from sqlalchemy import text

from aip.platform.context import RequestContext, use_context
from aip.platform.db.session import DbEngine as AsyncEngine
from aip.platform.db.session import as_jobs_role, with_tenant
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
    "error_summary",
    "failure_outcome",
]

logger = structlog.stdlib.get_logger(__name__)

LAST_ERROR_MAX = 500  # the column allows 4000; a summary never needs more
LEASE_EXPIRED = "lease expired before an outcome was recorded"
_ALERT_EVERY = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class DispatchSettings:
    """Dispatcher settings (module README); ``from_env`` reads the ``OUTBOX_*`` variables."""

    batch_size: int = 100
    poll_interval_s: int = 2
    max_attempts: int = 10
    backoff_base_s: float = 2.0
    backoff_cap_s: float = 3600.0
    lease_s: float = 300.0
    dead_letter_alert_threshold: int = 10
    alert_interval_s: float = 60.0
    max_batches_per_run: int = 50

    def __post_init__(self) -> None:
        if self.batch_size < 1 or self.max_attempts < 1 or self.max_batches_per_run < 1:
            raise ValueError("batch_size, max_attempts and max_batches_per_run must be >= 1")
        if not 1 <= self.poll_interval_s <= 59:
            raise ValueError("poll_interval_s must be between 1 and 59 seconds")
        if self.backoff_base_s <= 0 or self.backoff_cap_s < self.backoff_base_s:
            raise ValueError("backoff_base_s must be > 0 and backoff_cap_s >= backoff_base_s")
        if self.lease_s <= 0 or self.alert_interval_s < 0:
            raise ValueError("lease_s must be > 0 and alert_interval_s >= 0")
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


def error_summary(sub: Subscriber, exc: BaseException) -> str:
    """``<subscriber>: <ExceptionType> [sqlstate]``, never the message (it may hold tenant data)."""
    summary = f"{sub.name}: {type(exc).__name__}"
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(exc, "sqlstate", None)
    if orig is not None:
        summary += f" ({type(orig).__name__})"
    if isinstance(sqlstate, str):
        summary += f" [{sqlstate}]"
    return summary[:LAST_ERROR_MAX]


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
        super().__init__(error_summary(sub, cause))


_CLAIM = text("""
    WITH due AS (
      SELECT id
      FROM domain_events
      WHERE published_at IS NULL AND dead_lettered_at IS NULL AND discarded_at IS NULL
        AND (next_attempt_at IS NULL OR next_attempt_at <= now())
      ORDER BY occurred_at
      LIMIT :n
      FOR UPDATE SKIP LOCKED
    )
    UPDATE domain_events AS d
       SET attempts = d.attempts + 1,
           next_attempt_at = now() + make_interval(secs => :lease),
           dead_lettered_at = CASE WHEN d.attempts >= :max THEN now() END,
           last_error = CASE WHEN d.attempts >= :max THEN :expired ELSE d.last_error END
      FROM due
     WHERE d.id = due.id
    RETURNING d.id, d.tenant_id, d.project_id, d.asset_id, d.event_name, d.event_version,
              d.aggregate_type, d.aggregate_id, d.payload, d.actor_id, d.occurred_at, d.attempts,
              d.dead_lettered_at IS NOT NULL AS expired
""")
# ``published_at IS NULL`` guards: a lease that ran out may have let another dispatcher finish
# the event first; its outcome stands (and the write-once trigger would refuse a second publish).
_PUBLISHED = text(
    "UPDATE domain_events SET published_at = now() WHERE id = :id AND published_at IS NULL"
)
_FAILED = text("""
    UPDATE domain_events
       SET last_error = :error,
           next_attempt_at = now() + make_interval(secs => :delay),
           dead_lettered_at = CASE WHEN :dead THEN now() END
     WHERE id = :id AND published_at IS NULL
""")


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
    jobs_engine: AsyncEngine, event: DomainEvent, exc: SubscriberFailedError, s: DispatchSettings
) -> Outcome:
    outcome = failure_outcome(event.attempts, s.max_attempts)
    delay = backoff(event.attempts, s.backoff_base_s, s.backoff_cap_s)
    async with as_jobs_role(jobs_engine) as conn:
        await conn.execute(
            _FAILED,
            {
                "id": event.id,
                "error": str(exc),
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
        subscriber=exc.subscriber.name,
        attempts=event.attempts,
        outcome=str(outcome),
        exc_info=exc.cause,
    )
    return outcome


async def dispatch_batch(
    jobs_engine: AsyncEngine,
    app_engine: AsyncEngine,
    subscribers: SubscriberRegistry,
    settings: DispatchSettings | None = None,
) -> BatchResult:
    """Claim, deliver and record one batch; return what happened to it."""
    s = settings or DispatchSettings()
    async with as_jobs_role(jobs_engine) as claim:
        rows = (
            (
                await claim.execute(
                    _CLAIM,
                    {
                        "n": s.batch_size,
                        "lease": s.lease_s,
                        "max": s.max_attempts,
                        "expired": LEASE_EXPIRED,
                    },
                )
            )
            .mappings()
            .all()
        )
    # RETURNING has no order; deliver oldest first.
    rows = sorted(rows, key=lambda r: r["occurred_at"])
    published = retried = dead = 0
    for row in rows:
        values = {k: v for k, v in row.items() if k != "expired"}
        values["payload"] = MappingProxyType(dict(values["payload"]))
        event = DomainEvent(**values)
        if row["expired"]:
            logger.warning(
                "outbox event dead-lettered after its lease ran out",
                event_id=str(event.id),
                tenant_id=str(event.tenant_id),
                attempts=event.attempts - 1,
            )
            dead += 1
            continue
        subs = subscribers.for_event(event.event_name, event.event_version)
        try:
            if subs:
                await _deliver(app_engine, subs, event)
        except SubscriberFailedError as exc:
            if await _record_failure(jobs_engine, event, exc, s) is Outcome.DEAD_LETTER:
                dead += 1
            else:
                retried += 1
            continue
        async with as_jobs_role(jobs_engine) as conn:
            await conn.execute(_PUBLISHED, {"id": event.id})
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
    async with as_jobs_role(jobs_engine) as conn:
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


_last_alert_check: float | None = None


async def drain(
    jobs_engine: AsyncEngine,
    app_engine: AsyncEngine,
    subscribers: SubscriberRegistry,
    settings: DispatchSettings | None = None,
) -> BatchResult:
    """Dispatch batches until one comes back short (or ``max_batches_per_run``), then alert."""
    global _last_alert_check
    s = settings or DispatchSettings()
    total = BatchResult()
    for _ in range(s.max_batches_per_run):
        result = await dispatch_batch(jobs_engine, app_engine, subscribers, s)
        total += result
        if result.claimed < s.batch_size:
            break
    now = time.monotonic()
    if _last_alert_check is None or now - _last_alert_check >= s.alert_interval_s:
        _last_alert_check = now
        await alert_dead_letter_thresholds(jobs_engine, app_engine, s.dead_letter_alert_threshold)
    return total
