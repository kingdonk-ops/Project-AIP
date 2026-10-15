"""The ``dispatch_outbox`` periodic job on the ``outbox`` queue (ARCH-07, ADR 0003).

Procrastinate defers it every ``OUTBOX_POLL_INTERVAL_S`` seconds (default 2); a queueing lock keeps
at most one waiting at a time. Each run drains due events in batches until one comes back short
(``drain``), claiming as ``aip_jobs`` (``DATABASE_JOBS_URL``) and running subscribers as
``aip_app`` (``DATABASE_URL``) inside each event's tenant.

The subscribers are those of the modules this process loads (``AIP_MODULES_PACKAGE`` and
``AIP_DISABLED_MODULES``, as for the API). :func:`active_subscribers` loads them once and fails
if a module subscribes to an event its manifest does not list; the worker calls it at boot.
"""

from __future__ import annotations

import structlog

from aip.platform.db.engine import get_engine, get_jobs_engine
from aip.platform.events.dispatcher import DispatchSettings, drain
from aip.platform.events.registry import load_module_events, register_platform_events
from aip.platform.events.subscribers import (
    SubscriberRegistry,
    subscribers,
    verify_manifest_subscribers,
)
from aip.platform.jobs.app import app
from aip.platform.modules.registry import load_modules

__all__ = ["OUTBOX_QUEUE", "active_subscribers", "dispatch_outbox", "poll_cron"]

logger = structlog.stdlib.get_logger(__name__)

OUTBOX_QUEUE = "outbox"

_active: SubscriberRegistry | None = None


def poll_cron(interval_s: int) -> str:
    """A Procrastinate cron (six fields, the last is seconds) firing every ``interval_s``."""
    if not 1 <= interval_s <= 59:
        raise ValueError("the outbox poll interval must be between 1 and 59 seconds")
    return f"* * * * * */{interval_s}"


def active_subscribers() -> SubscriberRegistry:
    """The loaded modules' subscribers, checked against their manifests (cached)."""
    global _active
    if _active is None:
        modules = load_modules()
        load_module_events(modules)
        register_platform_events()
        verify_manifest_subscribers(modules)
        _active = subscribers.for_modules(module.id for module in modules)
    return _active


_SETTINGS = DispatchSettings.from_env()


@app.periodic(cron=poll_cron(_SETTINGS.poll_interval_s), periodic_id="dispatch_outbox")
@app.task(
    name="platform.dispatch_outbox",
    queue=OUTBOX_QUEUE,
    queueing_lock="platform.dispatch_outbox",
)
async def dispatch_outbox(timestamp: int) -> None:
    """Procrastinate entry point; ``timestamp`` is the scheduled time Procrastinate passes."""
    result = await drain(get_jobs_engine(), get_engine(), active_subscribers(), _SETTINGS)
    if result.claimed:
        logger.info(
            "outbox drained",
            claimed=result.claimed,
            published=result.published,
            retried=result.retried,
            dead_lettered=result.dead_lettered,
        )
