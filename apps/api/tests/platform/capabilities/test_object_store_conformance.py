"""ObjectStore conformance suite (STACK-02).

The same tests run against RustFS through the ``minio`` adapter and against LocalStack S3 through
the ``s3`` adapter. The store is always obtained from ``get_object_store()`` with only environment
variables differing, so calling code is identical for both backends.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest

from aip.platform.capabilities import (
    ObjectNotFoundError,
    ObjectStore,
    get_object_store,
    tenant_key,
)
from aip.platform.capabilities.adapters.minio import MinioObjectStore
from aip.platform.capabilities.adapters.s3 import S3ObjectStore

from .conftest import S3Backend

T1 = uuid.UUID("11111111-1111-4111-8111-111111111111")


@dataclass(frozen=True)
class StoreUnderTest:
    store: ObjectStore
    backend: S3Backend
    bucket: str


@pytest.fixture(params=["minio", "s3"])
def object_store(
    request: pytest.FixtureRequest, clean_capability_env: pytest.MonkeyPatch
) -> Iterator[StoreUnderTest]:
    backend: S3Backend = request.getfixturevalue(
        "rustfs" if request.param == "minio" else "localstack"
    )
    bucket = backend.create_bucket()
    for name, value in backend.env(bucket).items():
        clean_capability_env.setenv(name, value)
    store = get_object_store()
    expected = MinioObjectStore if request.param == "minio" else S3ObjectStore
    assert type(store) is expected
    yield StoreUnderTest(store, backend, bucket)


async def test_put_get_round_trip(object_store: StoreUnderTest) -> None:
    key = tenant_key(T1, "conformance", uuid.uuid4().hex, "a.pdf")
    body = b"%PDF-1.7 conformance \x00\xff"
    await object_store.store.put(key, body, content_type="application/pdf")
    assert await object_store.store.get(key) == body
    head = object_store.backend.boto("s3").head_object(Bucket=object_store.bucket, Key=key)
    assert head["ContentType"] == "application/pdf"


async def test_put_overwrites(object_store: StoreUnderTest) -> None:
    key = tenant_key(T1, "conformance", uuid.uuid4().hex, "b.txt")
    await object_store.store.put(key, b"one", content_type="text/plain")
    await object_store.store.put(key, b"two", content_type="text/plain")
    assert await object_store.store.get(key) == b"two"


async def test_presigned_put_then_presigned_get(object_store: StoreUnderTest) -> None:
    key = tenant_key(T1, "conformance", uuid.uuid4().hex, "c.bin")
    body = b"presigned body " + uuid.uuid4().bytes
    put = await object_store.store.presign_put(key, expires_s=300)
    assert put.method == "PUT"
    async with httpx.AsyncClient() as client:
        response = await client.put(put.url, content=body, headers=put.headers)
        assert response.status_code in (200, 204), response.text
        get = await object_store.store.presign_get(key, expires_s=300)
        assert get.method == "GET"
        response = await client.get(get.url, headers=get.headers)
        assert response.status_code == 200, response.text
        assert response.content == body
    assert await object_store.store.get(key) == body


async def test_delete_then_get_raises_not_found(object_store: StoreUnderTest) -> None:
    key = tenant_key(T1, "conformance", uuid.uuid4().hex, "d.txt")
    await object_store.store.put(key, b"x", content_type="text/plain")
    await object_store.store.delete(key)
    with pytest.raises(ObjectNotFoundError) as excinfo:
        await object_store.store.get(key)
    assert excinfo.value.key == key


async def test_delete_missing_key_is_idempotent(object_store: StoreUnderTest) -> None:
    await object_store.store.delete(tenant_key(T1, "conformance", uuid.uuid4().hex, "never"))


async def test_get_missing_key_raises_not_found(object_store: StoreUnderTest) -> None:
    key = tenant_key(T1, "conformance", uuid.uuid4().hex, "missing.pdf")
    with pytest.raises(ObjectNotFoundError):
        await object_store.store.get(key)


# --- SSE-KMS (ADR 0006) on LocalStack -----------------------------------------------------------


@pytest.fixture
def s3_store(
    localstack: S3Backend, clean_capability_env: pytest.MonkeyPatch
) -> Iterator[StoreUnderTest]:
    bucket = localstack.create_bucket()
    for name, value in localstack.env(bucket).items():
        clean_capability_env.setenv(name, value)
    yield StoreUnderTest(get_object_store(), localstack, bucket)


def _create_kms_key(backend: S3Backend) -> str:
    key = backend.boto("kms").create_key(Description=f"aip-test tenant {T1}")
    return key["KeyMetadata"]["Arn"]


async def test_put_with_kms_key_sets_sse_kms(s3_store: StoreUnderTest) -> None:
    kms_key = _create_kms_key(s3_store.backend)
    key = tenant_key(T1, "conformance", uuid.uuid4().hex, "kms.pdf")
    await s3_store.store.put(key, b"%PDF-kms", content_type="application/pdf", kms_key_id=kms_key)
    head = s3_store.backend.boto("s3").head_object(Bucket=s3_store.bucket, Key=key)
    assert head["ServerSideEncryption"] == "aws:kms"
    assert head["SSEKMSKeyId"] == kms_key
    assert await s3_store.store.get(key) == b"%PDF-kms"


async def test_presigned_put_with_kms_key_signs_sse_headers(s3_store: StoreUnderTest) -> None:
    kms_key = _create_kms_key(s3_store.backend)
    key = tenant_key(T1, "conformance", uuid.uuid4().hex, "kms-presigned.pdf")
    put = await s3_store.store.presign_put(key, expires_s=300, kms_key_id=kms_key)
    assert put.headers["x-amz-server-side-encryption"] == "aws:kms"
    assert put.headers["x-amz-server-side-encryption-aws-kms-key-id"] == kms_key
    assert "x-amz-server-side-encryption-aws-kms-key-id" in httpx.URL(put.url).params.get(
        "X-Amz-SignedHeaders", ""
    )
    async with httpx.AsyncClient() as client:
        response = await client.put(put.url, content=b"%PDF-presigned", headers=put.headers)
        assert response.status_code in (200, 204), response.text
    head = s3_store.backend.boto("s3").head_object(Bucket=s3_store.bucket, Key=key)
    assert head["SSEKMSKeyId"] == kms_key
