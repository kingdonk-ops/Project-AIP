"""Real backing services for the capability adapter tests (STACK-02). Nothing is mocked.

Each service is chosen in this order:

1. An environment URL (``AIP_TEST_RUSTFS_URL``, ``AIP_TEST_LOCALSTACK_URL``,
   ``AIP_TEST_GOTENBERG_URL``), for example a docker-compose stack or a CI service container.
2. A Testcontainers container when a Docker daemon is reachable (images pinned below; each can be
   overridden with ``AIP_TEST_<NAME>_IMAGE``).
3. Otherwise the test is skipped locally and fails under CI (``CI`` is set).

Credentials below are throwaway test-only values for local containers, not secrets.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import boto3  # pyright: ignore[reportMissingTypeStubs]
import httpx
import pytest
from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]

RUSTFS_IMAGE = os.environ.get("AIP_TEST_RUSTFS_IMAGE", "rustfs/rustfs:1.0.1")
# 4.x is the last LocalStack line that runs S3 and KMS without an auth token.
LOCALSTACK_IMAGE = os.environ.get("AIP_TEST_LOCALSTACK_IMAGE", "localstack/localstack:4.4")
GOTENBERG_IMAGE = os.environ.get("AIP_TEST_GOTENBERG_IMAGE", "gotenberg/gotenberg:8")

RUSTFS_KEY = "rustfsadmin"  # test-only default credentials of the RustFS image
LOCALSTACK_KEY = "test"  # LocalStack accepts any credentials
REGION = "ap-southeast-2"
RUSTFS_REGION = "us-east-1"  # the RustFS default region; S3-compatible servers sign with it


@dataclass(frozen=True)
class S3Backend:
    """An S3-compatible endpoint plus the adapter key that should talk to it."""

    adapter: str  # "minio" or "s3"
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    region: str = REGION

    def env(self, bucket: str) -> dict[str, str]:
        """Environment variables that select this backend through the factory."""
        env = {
            "OBJECT_STORE": self.adapter,
            "OBJECT_STORE_BUCKET": bucket,
            "OBJECT_STORE_ENDPOINT_URL": self.endpoint_url,
            "OBJECT_STORE_REGION": self.region,
            "OBJECT_STORE_ACCESS_KEY_ID": self.access_key_id,
            "OBJECT_STORE_SECRET_ACCESS_KEY": self.secret_access_key,
        }
        if self.adapter == "s3":
            env["OBJECT_STORE_ADDRESSING_STYLE"] = "path"
        return env

    def boto(self, service: str) -> Any:
        """A plain synchronous boto3 client, used only to arrange and inspect test state."""
        return boto3.client(  # pyright: ignore[reportUnknownMemberType]
            service,
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def create_bucket(self) -> str:
        name = f"aip-test-{uuid.uuid4().hex[:12]}"
        if self.region == "us-east-1":
            self.boto("s3").create_bucket(Bucket=name)
        else:
            self.boto("s3").create_bucket(
                Bucket=name, CreateBucketConfiguration={"LocationConstraint": self.region}
            )
        return name


def _docker_reachable() -> bool:
    try:
        import docker  # pyright: ignore[reportMissingTypeStubs]

        client: Any = docker.from_env()  # pyright: ignore[reportUnknownMemberType]
        client.ping()
        return True
    except Exception:
        return False


def _unavailable(what: str, env_var: str) -> None:
    message = f"no {what}: set {env_var} or start a Docker daemon"
    if os.environ.get("CI"):
        pytest.fail(message)
    pytest.skip(message)


def _wait_until(check: Callable[[], bool], what: str, timeout_s: float = 120) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"{what} did not become ready within {timeout_s:.0f}s")


@contextmanager
def _container(
    image: str, port: int, env: dict[str, str], ready: Callable[[str], bool], what: str
) -> Iterator[str]:
    """Run ``image`` and yield its base URL once ``ready(url)`` returns true."""
    from testcontainers.core.container import (  # pyright: ignore[reportMissingTypeStubs]
        DockerContainer,
    )

    container: Any = DockerContainer(image)
    container.with_exposed_ports(port)
    for key, value in env.items():
        container.with_env(key, value)
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(port)}"
        _wait_until(lambda: ready(url), what)
        yield url


def _s3_ready(backend: S3Backend) -> bool:
    backend.boto("s3").list_buckets()
    return True


def _localstack_ready(url: str) -> bool:
    services = httpx.get(f"{url}/_localstack/health", timeout=5).json().get("services", {})
    return all(services.get(s) in ("available", "running") for s in ("s3", "kms"))


def _gotenberg_ready(url: str) -> bool:
    return httpx.get(f"{url}/health", timeout=5).is_success


@pytest.fixture(scope="session")
def rustfs() -> Iterator[S3Backend]:
    """RustFS (S3-compatible, Apache-2.0), driven by the ``minio`` adapter."""
    url = os.environ.get("AIP_TEST_RUSTFS_URL")
    key = os.environ.get("AIP_TEST_RUSTFS_ACCESS_KEY", RUSTFS_KEY)
    secret = os.environ.get("AIP_TEST_RUSTFS_SECRET_KEY", RUSTFS_KEY)
    if url:
        yield S3Backend("minio", url, key, secret, RUSTFS_REGION)
        return
    if not _docker_reachable():
        _unavailable("RustFS", "AIP_TEST_RUSTFS_URL")
    env = {"RUSTFS_ACCESS_KEY": key, "RUSTFS_SECRET_KEY": secret}

    def ready(endpoint: str) -> bool:
        return _s3_ready(S3Backend("minio", endpoint, key, secret, RUSTFS_REGION))

    with _container(RUSTFS_IMAGE, 9000, env, ready, "RustFS") as endpoint:
        yield S3Backend("minio", endpoint, key, secret, RUSTFS_REGION)


@pytest.fixture(scope="session")
def localstack() -> Iterator[S3Backend]:
    """LocalStack S3 + KMS, driven by the ``s3`` adapter."""
    url = os.environ.get("AIP_TEST_LOCALSTACK_URL")
    if url:
        yield S3Backend("s3", url, LOCALSTACK_KEY, LOCALSTACK_KEY)
        return
    if not _docker_reachable():
        _unavailable("LocalStack", "AIP_TEST_LOCALSTACK_URL")
    env = {"SERVICES": "s3,kms", "AWS_DEFAULT_REGION": REGION}
    with _container(LOCALSTACK_IMAGE, 4566, env, _localstack_ready, "LocalStack") as endpoint:
        yield S3Backend("s3", endpoint, LOCALSTACK_KEY, LOCALSTACK_KEY)


@pytest.fixture(scope="session")
def gotenberg_url() -> Iterator[str]:
    url = os.environ.get("AIP_TEST_GOTENBERG_URL")
    if url:
        yield url.rstrip("/")
        return
    if not _docker_reachable():
        _unavailable("Gotenberg", "AIP_TEST_GOTENBERG_URL")
    with _container(GOTENBERG_IMAGE, 3000, {}, _gotenberg_ready, "Gotenberg") as endpoint:
        yield endpoint


@pytest.fixture
def clean_capability_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Remove every capability variable so a test sees only what it sets."""
    for name in list(os.environ):
        if name.startswith(("OBJECT_STORE", "PDF_RENDERER", "GOTENBERG_")):
            monkeypatch.delenv(name, raising=False)
    return monkeypatch
