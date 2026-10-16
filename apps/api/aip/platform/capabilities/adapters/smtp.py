"""SMTP ``Mailer`` (STACK-06): Coolify, dev and CI (Mailpit in compose).

Uses the standard library's ``smtplib`` in a worker thread, so it adds no dependency. STARTTLS when
``starttls`` is set; credentials only when both are given. The ``Message-ID`` is generated here and
returned, so the job records it and logs carry it instead of any address.
"""

from __future__ import annotations

import asyncio
import email.message
import email.utils
import re
import smtplib
import ssl

from aip.platform.capabilities.errors import MailError
from aip.platform.capabilities.protocols import EmailMessage

__all__ = ["SmtpMailer", "build_mime"]

# A Message-ID left part is a dot-atom: keep letters, digits, '.' and '-'.
_MSGID_UNSAFE = re.compile(r"[^A-Za-z0-9.-]")


def build_mime(message: EmailMessage, *, domain: str) -> email.message.EmailMessage:
    mime = email.message.EmailMessage()
    mime["From"] = message.sender
    mime["To"] = ", ".join(message.to)
    mime["Subject"] = message.subject
    idstring = _MSGID_UNSAFE.sub("-", message.idempotency_key)[:40]
    mime["Message-ID"] = email.utils.make_msgid(idstring=idstring, domain=domain)
    mime["X-AIP-Tenant"] = message.tenant_id
    mime.set_content(message.text)
    if message.html is not None:
        mime.add_alternative(message.html, subtype="html")
    return mime


class SmtpMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        starttls: bool = False,
        username: str | None = None,
        password: str | None = None,
        timeout_s: float = 30.0,
        domain: str = "aip.local",
    ) -> None:
        self._host = host
        self._port = port
        self._starttls = starttls
        self._username = username
        self._password = password
        self._timeout_s = timeout_s
        self._domain = domain

    def _send_blocking(self, mime: email.message.EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_s) as smtp:
            if self._starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(mime)

    async def send(self, message: EmailMessage) -> str:
        if not message.to:
            raise MailError("a message needs at least one recipient")
        mime = build_mime(message, domain=self._domain)
        try:
            await asyncio.to_thread(self._send_blocking, mime)
        except (OSError, smtplib.SMTPException) as exc:
            # The exception text can echo addresses (SMTPRecipientsRefused): keep only its type.
            raise MailError(f"SMTP send failed: {type(exc).__name__}") from None
        return str(mime["Message-ID"]).strip("<>")
