"""Background jobs the ops module owns (OPS-02 registry, ADR 0003).

``ops.send_email`` (STACK-06): every transactional email goes through this job, never inside a
request. ``send_email`` queues it in the caller's transaction (the message sits in the job's
RLS-protected payload); the job sends through the configured ``Mailer`` (``MAILER=smtp|ses``),
retries with backoff, and ends ``failed`` after its last try instead of losing the message. The
job's ``result_ref`` is ``mail:<message id>``. Logs carry the message id, tenant and job id only:
never an address, subject or body.

Delivery is at least once: a send that succeeded just before the worker died is sent again on the
retry, because neither SMTP nor SES can deduplicate on our key.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from aip.platform.capabilities import CapabilitySettings, EmailMessage, Mailer, get_mailer

from .enqueue import enqueue
from .registry import register, registered_types
from .schemas import JobView

__all__ = ["SEND_EMAIL", "send_email"]

logger = logging.getLogger(__name__)

SEND_EMAIL = "ops.send_email"
SEND_EMAIL_MAX_ATTEMPTS = 5
SEND_EMAIL_BACKOFF_S = 30

# The mailer the job uses; tests replace it.
mailer_factory: Callable[[], Mailer] = get_mailer


def _message(job: JobView) -> EmailMessage:
    payload: dict[str, Any] = job.payload
    return EmailMessage(
        sender=payload["from"],
        to=tuple(payload["to"]),
        subject=payload["subject"],
        text=payload["text"],
        html=payload.get("html"),
        tenant_id=str(job.tenant_id),
        idempotency_key=job.idempotency_key or str(job.id),
    )


async def _send(conn: AsyncConnection, job: JobView) -> str | None:
    del conn  # the send touches no tenant rows
    message_id = await mailer_factory().send(_message(job))
    # The id's domain part (after '@') is dropped so no log line ever carries an address-like value.
    logger.info(
        "mail sent: message %s, tenant %s, job %s", message_id.split("@")[0], job.tenant_id, job.id
    )
    return f"mail:{message_id}"


if SEND_EMAIL not in registered_types():
    register(
        SEND_EMAIL,
        _send,
        queue="default",
        timeout_s=60,
        max_attempts=SEND_EMAIL_MAX_ATTEMPTS,
        retry_backoff_s=SEND_EMAIL_BACKOFF_S,
    )


async def send_email(
    conn: AsyncConnection,
    *,
    to: Sequence[str],
    subject: str,
    text: str,
    idempotency_key: str,
    html: str | None = None,
    sender: str | None = None,
) -> JobView:
    """Queue one email in the caller's transaction; the same ``idempotency_key`` queues it once."""
    if not to:
        raise ValueError("an email needs at least one recipient")
    if not idempotency_key:
        raise ValueError("an email needs an idempotency key")
    payload: dict[str, Any] = {
        "from": sender or CapabilitySettings().mail_from,
        "to": list(to),
        "subject": subject,
        "text": text,
        "html": html,
    }
    return await enqueue(conn, SEND_EMAIL, payload, idempotency_key=f"mail:{idempotency_key}")
