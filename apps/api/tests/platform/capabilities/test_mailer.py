"""STACK-06: the Mailer capability: adapter selection, SMTP to Mailpit, SES to LocalStack."""

from __future__ import annotations

import uuid
from typing import Any

import boto3  # pyright: ignore[reportMissingTypeStubs]
import pytest

from aip.platform.capabilities import (
    CapabilitySettings,
    EmailMessage,
    MailError,
    UnknownAdapterError,
    get_mailer,
    validate_capability_settings,
)
from aip.platform.capabilities.adapters.ses import SesMailer
from aip.platform.capabilities.adapters.smtp import SmtpMailer, build_mime
from tests.platform.capabilities.conftest import REGION, Mailpit, S3Backend


def message(**overrides: object) -> EmailMessage:
    values: dict[str, object] = {
        "sender": "AIP <no-reply@kaefer.test>",
        "to": ("alice@kaefer.test",),
        "subject": f"Isolation probe {uuid.uuid4().hex[:8]}",
        "text": "Hello from AIP",
        "tenant_id": "00000000-0000-4000-8000-00000000000a",
        "idempotency_key": "mail:invite:42",
        "html": "<p>Hello from <b>AIP</b></p>",
    }
    values.update(overrides)
    return EmailMessage(**values)  # type: ignore[arg-type]


# --- unit: selection ----------------------------------------------------------------------------


def test_smtp_is_the_default_and_ses_is_selected_by_mailer(
    clean_capability_env: pytest.MonkeyPatch,
) -> None:
    assert isinstance(get_mailer(CapabilitySettings()), SmtpMailer)
    clean_capability_env.setenv("MAILER", "SES")
    assert isinstance(get_mailer(CapabilitySettings()), SesMailer)


def test_an_unknown_mailer_stops_startup(clean_capability_env: pytest.MonkeyPatch) -> None:
    clean_capability_env.setenv("MAILER", "nope")
    with pytest.raises(UnknownAdapterError, match="MAILER='nope'"):
        validate_capability_settings(CapabilitySettings())
    with pytest.raises(UnknownAdapterError):
        get_mailer(CapabilitySettings())


def test_the_smtp_password_is_secret(clean_capability_env: pytest.MonkeyPatch) -> None:
    clean_capability_env.setenv("SMTP_PASSWORD", "hunter2")
    settings = CapabilitySettings()
    assert "hunter2" not in repr(settings)
    assert settings.smtp_password is not None
    assert settings.smtp_password.get_secret_value() == "hunter2"


def test_the_mime_message_has_a_valid_message_id_and_both_parts() -> None:
    mime = build_mime(message(), domain="aip.test")
    message_id = str(mime["Message-ID"])
    assert message_id.startswith("<") and message_id.endswith("@aip.test>")
    assert ":" not in message_id
    assert mime["X-AIP-Tenant"] == "00000000-0000-4000-8000-00000000000a"
    assert [part.get_content_type() for part in mime.iter_parts()] == ["text/plain", "text/html"]


async def test_a_message_without_recipients_is_refused_before_any_network() -> None:
    with pytest.raises(MailError, match="recipient"):
        await SmtpMailer(host="127.0.0.1", port=9).send(message(to=()))
    with pytest.raises(MailError, match="recipient"):
        await SesMailer(endpoint_url="http://127.0.0.1:9").send(message(to=()))


async def test_an_smtp_failure_names_no_address() -> None:
    with pytest.raises(MailError) as caught:
        await SmtpMailer(host="127.0.0.1", port=9, timeout_s=2).send(message())
    assert "@" not in str(caught.value)


# --- integration --------------------------------------------------------------------------------


async def test_smtp_delivers_to_mailpit(mailpit: Mailpit) -> None:
    mailpit.clear()
    sent = message()
    mailer = SmtpMailer(host=mailpit.smtp_host, port=mailpit.smtp_port)
    message_id = await mailer.send(sent)
    [delivered] = [m for m in mailpit.messages() if m["Subject"] == sent.subject]
    assert delivered["MessageID"] == message_id
    assert [a["Address"] for a in delivered["To"]] == ["alice@kaefer.test"]


async def test_ses_sends_through_localstack(
    localstack: S3Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", localstack.access_key_id)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", localstack.secret_access_key)
    ses: Any = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "ses",
        endpoint_url=localstack.endpoint_url,
        region_name=REGION,
        aws_access_key_id=localstack.access_key_id,
        aws_secret_access_key=localstack.secret_access_key,
    )
    ses.verify_email_identity(EmailAddress="no-reply@kaefer.test")
    mailer = SesMailer(region=REGION, endpoint_url=localstack.endpoint_url)
    message_id = await mailer.send(message(sender="no-reply@kaefer.test"))
    assert message_id
