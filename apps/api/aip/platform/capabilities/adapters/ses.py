"""Amazon SES ``Mailer`` (STACK-06): AWS, ``ap-southeast-2``.

The SES ``SendEmail`` API (v1: fully supported by AWS and the one LocalStack's community edition
emulates). Credentials come from the default chain (the ECS task role in AWS; ``AWS_*`` variables
against LocalStack). ``configuration_set`` routes delivery events;
the tenant goes on the message as the ``tenant`` tag. ``endpoint_url`` is for LocalStack only.
"""

from __future__ import annotations

import re
from typing import Any, cast

import aioboto3  # pyright: ignore[reportMissingTypeStubs]
from botocore.exceptions import BotoCoreError, ClientError

from aip.platform.capabilities.errors import MailError
from aip.platform.capabilities.protocols import EmailMessage

__all__ = ["SesMailer"]

# SES message tag values allow letters, digits, '_', '-' and '.' only.
_TAG_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


class SesMailer:
    def __init__(
        self,
        *,
        region: str = "ap-southeast-2",
        endpoint_url: str | None = None,
        configuration_set: str | None = None,
    ) -> None:
        self._region = region
        self._endpoint_url = endpoint_url
        self._configuration_set = configuration_set
        self._session = aioboto3.Session()

    def _request(self, message: EmailMessage) -> dict[str, Any]:
        body: dict[str, Any] = {"Text": {"Data": message.text, "Charset": "UTF-8"}}
        if message.html is not None:
            body["Html"] = {"Data": message.html, "Charset": "UTF-8"}
        request: dict[str, Any] = {
            "Source": message.sender,
            "Destination": {"ToAddresses": list(message.to)},
            "Message": {"Subject": {"Data": message.subject, "Charset": "UTF-8"}, "Body": body},
            "Tags": [{"Name": "tenant", "Value": _TAG_UNSAFE.sub("_", message.tenant_id)}],
        }
        if self._configuration_set:
            request["ConfigurationSetName"] = self._configuration_set
        return request

    async def send(self, message: EmailMessage) -> str:
        if not message.to:
            raise MailError("a message needs at least one recipient")
        client_args: dict[str, Any] = {"region_name": self._region}
        if self._endpoint_url:
            client_args["endpoint_url"] = self._endpoint_url
        try:
            client = cast(Any, self._session.client("ses", **client_args))  # pyright: ignore[reportUnknownMemberType]
            async with client as ses:
                response: dict[str, Any] = await ses.send_email(**self._request(message))
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "unknown")
            raise MailError(f"SES send failed: {code}") from None
        except BotoCoreError as exc:
            raise MailError(f"SES send failed: {type(exc).__name__}") from None
        return str(response["MessageId"])
