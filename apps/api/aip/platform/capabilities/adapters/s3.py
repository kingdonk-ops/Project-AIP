"""``ObjectStore`` on AWS S3 (and LocalStack) via aioboto3 (STACK-02).

With ``kms_key_id`` set, puts and presigned PUTs request ``ServerSideEncryption=aws:kms`` with
``SSEKMSKeyId`` (header ``x-amz-server-side-encryption-aws-kms-key-id``), per ADR 0006. For a
presigned PUT those headers are signed, so the client must send ``PresignedRequest.headers``.

A client is opened per call: aioboto3 clients are bound to an event loop, and presigning is local.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Literal

import aioboto3
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError

from aip.platform.capabilities.errors import ObjectNotFoundError
from aip.platform.capabilities.keys import ObjectKey
from aip.platform.capabilities.protocols import PresignedRequest

if TYPE_CHECKING:
    from types_aiobotocore_s3.client import S3Client

AddressingStyle = Literal["auto", "virtual", "path"]

SSE_HEADER = "x-amz-server-side-encryption"
SSE_KMS_KEY_HEADER = "x-amz-server-side-encryption-aws-kms-key-id"
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "404", "NotFound"})


class S3ObjectStore:
    """S3 adapter. ``endpoint_url=None`` means AWS; set it for LocalStack."""

    addressing_style: AddressingStyle = "auto"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        addressing_style: AddressingStyle | None = None,
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url
        if addressing_style is not None:
            self.addressing_style = addressing_style
        # Without explicit keys boto's default chain applies (ECS task role in production).
        self._session = aioboto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

    @asynccontextmanager
    async def _client(self) -> AsyncGenerator[S3Client]:
        config = AioConfig(
            signature_version="s3v4",
            s3={"addressing_style": self.addressing_style},
            retries={"max_attempts": 3, "mode": "standard"},
        )
        # The stubs type the "s3" overload; only the other services' overloads are unknown.
        async with self._session.client(  # pyright: ignore[reportUnknownMemberType]
            "s3", endpoint_url=self.endpoint_url, region_name=self.region, config=config
        ) as client:
            yield client

    @staticmethod
    def _sse_params(kms_key_id: str | None) -> dict[str, Any]:
        if kms_key_id is None:
            return {}
        if not kms_key_id:
            raise ValueError("kms_key_id must not be empty")
        return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": kms_key_id}

    async def put(
        self, key: ObjectKey, body: bytes, *, content_type: str, kms_key_id: str | None = None
    ) -> None:
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                **self._sse_params(kms_key_id),
            )

    async def get(self, key: ObjectKey) -> bytes:
        async with self._client() as s3:
            try:
                response = await s3.get_object(Bucket=self.bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                    raise ObjectNotFoundError(key) from None
                raise
            async with response["Body"] as stream:
                return await stream.read()

    async def presign_put(
        self, key: ObjectKey, *, expires_s: int, kms_key_id: str | None = None
    ) -> PresignedRequest:
        sse = self._sse_params(kms_key_id)
        async with self._client() as s3:
            url = await s3.generate_presigned_url(
                "put_object",
                Params={"Bucket": self.bucket, "Key": key, **sse},
                ExpiresIn=expires_s,
                HttpMethod="PUT",
            )
        headers: dict[str, str] = {}
        if kms_key_id is not None:
            headers = {SSE_HEADER: "aws:kms", SSE_KMS_KEY_HEADER: kms_key_id}
        return PresignedRequest(method="PUT", url=url, headers=headers)

    async def presign_get(self, key: ObjectKey, *, expires_s: int) -> PresignedRequest:
        async with self._client() as s3:
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_s,
                HttpMethod="GET",
            )
        return PresignedRequest(method="GET", url=url)

    async def delete(self, key: ObjectKey) -> None:
        async with self._client() as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)
