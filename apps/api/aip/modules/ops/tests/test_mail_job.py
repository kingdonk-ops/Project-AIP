"""STACK-06: the ``ops.send_email`` job (queued in the caller's transaction, retried, delivered once).

The worker runs in-process as ``aip_jobs`` (OPS-02 fixtures). The job's handler is registered again
under a fresh type with no retry backoff, so a failing send retries at once.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import text
from tests.conftest import TENANT_A_ID
from tests.platform.db.conftest import FreshDb

from aip.modules.ops import api as ops
from aip.modules.ops import jobs as mail_jobs
from aip.modules.ops import registry
from aip.modules.ops.tests.test_runner import (  # noqa: F401 - re-exported fixtures and helpers
    Tx,
    _dispose_jobs_engine,  # pyright: ignore[reportPrivateUsage]
    drain,
    job_row,
    queue_db,
    tx,
)
from aip.platform.capabilities import EmailMessage, MailError


class FlakyMailer:
    """Fails the first ``failures`` sends, then records each delivery."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.delivered: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> str:
        if self.failures:
            self.failures -= 1
            raise MailError("SMTP send failed: SMTPServerDisconnected")
        self.delivered.append(message)
        return f"{uuid.uuid4().hex}@aip.test"


@pytest.fixture
def mail_type() -> Iterator[str]:
    """``ops.send_email``'s handler under a test type with five tries and no backoff."""
    name = f"test.mail.{uuid.uuid4().hex[:10]}"
    ops.register(name, mail_jobs._send, timeout_s=30, max_attempts=5, retry_backoff_s=0)  # pyright: ignore[reportPrivateUsage]
    yield name
    registry.unregister(name)


@pytest.fixture
def mailer(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], FlakyMailer]:
    def install(failures: int) -> FlakyMailer:
        fake = FlakyMailer(failures)
        monkeypatch.setattr(mail_jobs, "mailer_factory", lambda: fake)
        return fake

    return install


PAYLOAD: dict[str, Any] = {
    "from": "AIP <no-reply@kaefer.test>",
    "to": ["alice@kaefer.test"],
    "subject": "Your export is ready",
    "text": "Open AIP to download it.",
    "html": None,
}


async def test_send_email_queues_one_job_per_idempotency_key(queue_db: FreshDb, tx: Tx) -> None:
    async with tx(TENANT_A_ID) as conn:
        first = await ops.send_email(
            conn, to=["alice@kaefer.test"], subject="Hi", text="Body", idempotency_key="invite:1"
        )
        again = await ops.send_email(
            conn, to=["alice@kaefer.test"], subject="Hi", text="Body", idempotency_key="invite:1"
        )
    assert first.id == again.id
    assert (first.job_type, first.status.value) == (ops.SEND_EMAIL, "queued")
    assert first.payload["to"] == ["alice@kaefer.test"]
    assert first.payload["from"]


async def test_send_email_refuses_a_message_without_recipient_or_key(tx: Tx) -> None:
    async with tx(TENANT_A_ID) as conn:
        with pytest.raises(ValueError, match="recipient"):
            await ops.send_email(conn, to=[], subject="s", text="t", idempotency_key="k")
        with pytest.raises(ValueError, match="idempotency"):
            await ops.send_email(conn, to=["a@kaefer.test"], subject="s", text="t", idempotency_key="")


async def test_a_send_that_fails_twice_then_succeeds_is_delivered_once(
    queue_db: FreshDb,
    tx: Tx,
    mail_type: str,
    mailer: Callable[[int], FlakyMailer],
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = mailer(2)
    async with tx(TENANT_A_ID) as conn:
        job = await ops.enqueue(conn, mail_type, PAYLOAD, idempotency_key="mail:export:7")
    with caplog.at_level(logging.INFO):
        await drain(queue_db)

    assert [m.subject for m in fake.delivered] == ["Your export is ready"]
    delivered = fake.delivered[0]
    assert (delivered.tenant_id, delivered.idempotency_key) == (str(TENANT_A_ID), "mail:export:7")
    row = await job_row(tx, TENANT_A_ID, job.id)
    assert (row.status, row.attempts) == ("succeeded", 3)
    assert str(row.result_ref).startswith("mail:")
    sent_lines = [r.getMessage() for r in caplog.records if r.name == "aip.modules.ops.jobs"]
    assert len(sent_lines) == 1
    assert all("@" not in line for line in sent_lines)


async def test_a_send_that_never_succeeds_ends_failed_not_lost(
    queue_db: FreshDb, tx: Tx, mail_type: str, mailer: Callable[[int], FlakyMailer]
) -> None:
    fake = mailer(99)
    async with tx(TENANT_A_ID) as conn:
        job = await ops.enqueue(conn, mail_type, PAYLOAD, idempotency_key="mail:export:8")
    await drain(queue_db)
    row = await job_row(tx, TENANT_A_ID, job.id)
    assert (row.status, row.attempts) == ("failed", 5)
    assert "@" not in str(row.error)
    assert fake.delivered == []
    async with tx(TENANT_A_ID) as conn:
        payload = (
            await conn.execute(text("SELECT payload FROM jobs WHERE id = :i"), {"i": job.id})
        ).scalar_one()
    assert payload["subject"] == "Your export is ready"  # the message is kept for a retry
