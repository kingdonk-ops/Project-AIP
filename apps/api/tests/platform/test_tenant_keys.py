"""TENANCY-02: two tenants can never produce the same key, in any namespace."""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Callable

import pytest

from aip.platform.tenant_keys import (
    TenantId,
    TenantKeyError,
    embedding_namespace,
    job_lock,
    job_queueing_lock,
    pubsub_channel,
    redis_key,
    s3_key,
    search_index,
)

A = "00000000-0000-7000-8000-000000000001"
B = "00000000-0000-7000-8000-000000000002"
REGION = "eu-central-1"

# Safe names stay tenant-bound; unsafe ones (hostile callers) must raise.
SAFE_NAMES = ["x", "x.pdf", "Ünïcödé", "日本語", "a" * 255, "a-b_c", "x.y.z", "emoji😀"]
UNSAFE_NAMES = [
    "",
    "..",
    "a/b",
    "/",
    "../x",
    "x/../y",
    "a:b",
    ":",
    "a b",
    " ",
    "a\tb",
    "a\nb",
    "a\x00b",
    "a\\b",
    "a" * 256,
    "a*",
    "a?",
    "x\u200b",  # zero-width space
    "x\u2028y",
    f"tenant:{B}:x",
    f"tenants/{B}/x",
]

BUILDERS: dict[str, Callable[[object, str], str]] = {
    "redis": lambda t, n: redis_key(t, "asset", n),
    "redis_single": lambda t, n: redis_key(t, n),
    "pubsub": lambda t, n: pubsub_channel(t, n),
    "job_lock": lambda t, n: job_lock(t, "export", n),
    "job_queueing_lock": lambda t, n: job_queueing_lock(t, "export", n),
    "s3": lambda t, n: s3_key(t, REGION, "docs", n),
}


def test_documented_formats() -> None:
    assert redis_key(A, "asset", "42") == f"tenant:{A}:asset:42"
    assert job_lock(A, "export", "slot-1") == f"tenant:{A}:job:export:slot-1"
    assert pubsub_channel(A, "events") == f"tenant:{A}:pubsub:events"
    assert s3_key(A, REGION, "docs", "x.pdf") == f"tenants/{A}/{REGION}/docs/x.pdf"
    assert search_index(A, "assets") == f"tenant-{A}-assets"
    assert embedding_namespace(A) == f"tenant:{A}:embedding"


@pytest.mark.parametrize(
    "bad",
    [None, "", " ", "x", "not-a-uuid", 42, b"x", [], A + "0", "{" + A + "}", "urn:uuid:" + A],
)
def test_bad_tenant_rejected_everywhere(bad: object) -> None:
    for build in BUILDERS.values():
        with pytest.raises(TenantKeyError):
            build(bad, "x")
    with pytest.raises(TenantKeyError):
        search_index(bad, "assets")
    with pytest.raises(TenantKeyError):
        embedding_namespace(bad)


def test_nil_uuid_rejected() -> None:
    for nil in (uuid.UUID(int=0), str(uuid.UUID(int=0))):
        with pytest.raises(TenantKeyError):
            redis_key(nil, "x")


def test_one_spelling_per_tenant() -> None:
    assert (
        redis_key(A.upper(), "x")
        == redis_key(A, "x")
        == redis_key(uuid.UUID(A), "x")
        == redis_key(TenantId(A), "x")
    )
    assert TenantId(A) == TenantId(A.upper())
    assert hash(TenantId(A)) == hash(TenantId(A.upper()))
    assert TenantId(A) != TenantId(B)
    with pytest.raises(AttributeError):
        TenantId(A).foo = 1  # type: ignore[attr-defined]


@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_unsafe_parts_rejected(name: str) -> None:
    for build in BUILDERS.values():
        with pytest.raises(TenantKeyError):
            build(A, name)


def test_non_string_and_missing_parts_rejected() -> None:
    with pytest.raises(TenantKeyError):
        redis_key(A)
    with pytest.raises(TenantKeyError):
        redis_key(A, 5)  # type: ignore[arg-type]
    with pytest.raises(TenantKeyError):
        job_lock(A, "export")
    with pytest.raises(TenantKeyError):
        s3_key(A, REGION)


def test_s3_bad_region_and_length() -> None:
    for region in ("", "EU", "eu/1", "..", "eu central", "1eu"):
        with pytest.raises(TenantKeyError):
            s3_key(A, region, "x")
    with pytest.raises(TenantKeyError):
        s3_key(A, REGION, *["a" * 200] * 6)
    with pytest.raises(TenantKeyError):
        s3_key(A, REGION, "..", "x")


@pytest.mark.parametrize("name", ["", "A", "a-b", "a b", "a/b", "x" * 65, "ü"])
def test_search_index_name_rejected(name: str) -> None:
    with pytest.raises(TenantKeyError):
        search_index(A, name)


def test_reserved_redis_heads() -> None:
    for head in ("job", "queueing", "pubsub", "embedding"):
        with pytest.raises(TenantKeyError):
            redis_key(A, head, "x")


@pytest.mark.parametrize("namespace", sorted(BUILDERS))
def test_two_tenants_never_collide_per_namespace(namespace: str) -> None:
    build = BUILDERS[namespace]
    tenants = [str(uuid.UUID(int=i)) for i in range(1, 6)] + [A, B]
    keys: dict[str, tuple[str, str]] = {}
    for tenant, name in itertools.product(tenants, SAFE_NAMES):
        key = build(tenant, name)
        assert key not in keys, f"collision on {key!r}"
        keys[key] = (tenant, name)
    assert len(keys) == len(tenants) * len(SAFE_NAMES)


CROSS: dict[str, Callable[[str, str], str]] = {
    "redis": lambda t, n: redis_key(t, n),
    "redis2": lambda t, n: redis_key(t, "asset", n),
    "pubsub": lambda t, n: pubsub_channel(t, n),
    "lock": lambda t, n: job_lock(t, n, "s"),
    "qlock": lambda t, n: job_queueing_lock(t, n, "s"),
    "s3": lambda t, n: s3_key(t, REGION, n),
    "search": lambda t, n: search_index(t, n),
}


def test_no_collision_across_namespaces() -> None:
    seen: dict[str, str] = {}
    for tenant, n, (label, make) in itertools.product(
        (A, B), ["x", "job", "export", "events", "embedding", "docs"], CROSS.items()
    ):
        try:
            key = make(tenant, n)
        except TenantKeyError:
            continue
        assert key not in seen, f"{label} collides with {seen[key]}"
        seen[key] = f"{tenant}/{label}/{n}"


def test_parts_cannot_shift_boundaries() -> None:
    assert redis_key(A, "a", "b") != redis_key(A, "ab")
    assert s3_key(A, REGION, "a", "b") != s3_key(A, REGION, "ab")
    assert job_lock(A, "t", "a", "b") != job_lock(A, "t", "ab")


def test_tenant_prefix_always_leads() -> None:
    long_name = "n" * 255
    for build in BUILDERS.values():
        key = build(A, long_name)
        assert key.startswith((f"tenant:{A}:", f"tenants/{A}/"))
