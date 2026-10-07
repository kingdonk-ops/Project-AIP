"""``ObjectStore`` on an S3-compatible endpoint: RustFS or MinIO on Coolify and in dev (STACK-02).

Same S3 API as the ``s3`` adapter, but it always talks to an explicit endpoint with path-style
addressing (``http://host:9000/<bucket>/<key>``), which these servers expect.

SSE-KMS: ``kms_key_id`` is passed through unchanged. The server must have a KMS configured
(MinIO KES, RustFS KMS) or it rejects the request; it is never silently dropped.
"""

from __future__ import annotations

from aip.platform.capabilities.adapters.s3 import S3ObjectStore


class MinioObjectStore(S3ObjectStore):
    addressing_style = "path"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        if not endpoint_url:
            raise ValueError("the minio adapter needs OBJECT_STORE_ENDPOINT_URL")
        super().__init__(
            bucket=bucket,
            region=region,
            endpoint_url=endpoint_url,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            addressing_style="path",
        )
