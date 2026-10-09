"""Tenant-scoped key builders (TENANCY-02): the only place that builds a tenant-prefixed key.

Caches, queues and locks, object storage and search must never share a key between tenants
(ADR 0006: prefixes are the second isolation layer behind the per-tenant KMS key). The design
makes a cross-tenant collision impossible by construction:

* ``TenantId`` is the one validated tenant-id type. It holds a real, non-nil UUID and always
  renders in the canonical lower-case hyphenated form, so one tenant has exactly one spelling.
* Every key is ``<fixed prefix with the tenant id><SEP><part><SEP><part>...``. Parts may not
  contain the separators (``:`` ``/``), whitespace, control characters, a backslash, glob
  characters or ``..``, so a part can never smuggle in a separator, a second tenant id or a path
  traversal. The tenant id is fixed-width (36 characters) and sits first, so two keys from
  different tenants differ inside the prefix and two keys of one tenant differ only through
  their (separator-free) parts. That makes every builder injective.
* One builder per namespace; each namespace has its own fixed marker, so a redis cache key can
  never equal a job lock, a pub/sub channel or an S3 key.

Nothing outside this module may assemble ``tenant:`` / ``tenants/`` strings by hand: the
architecture test ``tests/arch/test_tenant_key_boundary.py`` fails if it does.

``aip.platform`` never imports ``aip.modules`` (ADR 0004); this module imports only the stdlib.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Final, Self

__all__ = [
    "TenantId",
    "TenantKeyError",
    "embedding_namespace",
    "job_lock",
    "job_queueing_lock",
    "pubsub_channel",
    "redis_key",
    "s3_key",
    "search_index",
]

MAX_PART_LENGTH: Final = 255
# S3 object keys are at most 1024 bytes (UTF-8).
MAX_S3_KEY_BYTES: Final = 1024
MAX_KEY_LENGTH: Final = 1024

_CANONICAL_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_FORBIDDEN_CHARS = frozenset(":/\\*?[]{}\x7f")
_FORBIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_REGION = re.compile(r"[a-z]{2,}(?:-[a-z0-9]+)*")
_SEARCH_NAME = re.compile(r"[a-z0-9_]{1,64}")

# First part of a ``redis_key`` that would land in another builder's namespace.
_RESERVED_REDIS_HEADS: Final = frozenset({"job", "queueing", "pubsub", "embedding"})


class TenantKeyError(ValueError):
    """A tenant id or key part is missing, malformed or unsafe. Fail closed: never build the key."""


class TenantId:
    """A validated, non-nil tenant UUID in canonical lower-case form. Immutable and hashable."""

    __slots__ = ("_uuid",)
    _uuid: uuid.UUID

    def __init__(self, value: object) -> None:
        object.__setattr__(self, "_uuid", self._parse(value))

    @staticmethod
    def _parse(value: object) -> uuid.UUID:
        if isinstance(value, TenantId):
            return value._uuid
        if isinstance(value, uuid.UUID):
            parsed = value
        elif isinstance(value, str):
            if not _CANONICAL_UUID.fullmatch(value):
                raise TenantKeyError("tenant id must be a canonical hyphenated uuid")
            parsed = uuid.UUID(value)
        else:
            raise TenantKeyError("tenant id is missing or has the wrong type")
        if parsed.int == 0:
            raise TenantKeyError("tenant id must not be the nil uuid")
        return parsed

    @classmethod
    def parse(cls, value: object) -> Self:
        return cls(value)

    @property
    def uuid(self) -> uuid.UUID:
        return self._uuid

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("TenantId is immutable")

    def __str__(self) -> str:
        return str(self._uuid)

    def __repr__(self) -> str:
        return f"TenantId({self._uuid})"

    def __hash__(self) -> int:
        return hash(self._uuid)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TenantId) and other._uuid == self._uuid


def _part(value: object, what: str = "key part") -> str:
    if not isinstance(value, str):
        raise TenantKeyError(f"{what} must be a string")
    if not value:
        raise TenantKeyError(f"{what} must not be empty")
    if len(value) > MAX_PART_LENGTH:
        raise TenantKeyError(f"{what} is longer than {MAX_PART_LENGTH} characters")
    if ".." in value:
        raise TenantKeyError(f"{what} must not contain '..'")
    for ch in value:
        if (
            ch in _FORBIDDEN_CHARS
            or ch.isspace()
            or unicodedata.category(ch) in _FORBIDDEN_CATEGORIES
        ):
            raise TenantKeyError(f"{what} contains a forbidden character")
    return value


def _parts(parts: tuple[object, ...], what: str = "key part") -> list[str]:
    if not parts:
        raise TenantKeyError(f"at least one {what} is required")
    return [_part(p, what) for p in parts]


def _bounded(key: str) -> str:
    if len(key) > MAX_KEY_LENGTH:
        raise TenantKeyError("key is too long")
    return key


def redis_key(tenant_id: object, *parts: str) -> str:
    """Cache, rate-limit and session-cache key: ``tenant:<id>:<part>:<part>...``."""
    tid = TenantId.parse(tenant_id)
    segments = _parts(parts)
    if segments[0] in _RESERVED_REDIS_HEADS:
        raise TenantKeyError(f"'{segments[0]}' is reserved for another key namespace")
    return _bounded(":".join(("tenant", str(tid), *segments)))


def pubsub_channel(tenant_id: object, name: str) -> str:
    """Pub/sub channel: ``tenant:<id>:pubsub:<name>``."""
    tid = TenantId.parse(tenant_id)
    return _bounded(f"tenant:{tid}:pubsub:{_part(name, 'channel name')}")


def _job(kind: str, tenant_id: object, job_type: str, parts: tuple[str, ...]) -> str:
    tid = TenantId.parse(tenant_id)
    segments = [_part(job_type, "job type"), *_parts(parts, "lock slot")]
    return _bounded(":".join(("tenant", str(tid), kind, *segments)))


def job_lock(tenant_id: object, job_type: str, *parts: str) -> str:
    """Procrastinate ``lock``: ``tenant:<id>:job:<type>:<slot>...`` (format fixed by OPS-02)."""
    return _job("job", tenant_id, job_type, parts)


def job_queueing_lock(tenant_id: object, job_type: str, *parts: str) -> str:
    """Procrastinate ``queueing_lock``: ``tenant:<id>:queueing:<type>:<slot>...``."""
    return _job("queueing", tenant_id, job_type, parts)


def s3_key(tenant_id: object, region_code: str, *parts: str) -> str:
    """Object key: ``tenants/<id>/<region>/<part>/<part>...``.

    ``region_code`` is the tenant's deployment region (for example ``eu-central-1``). The last
    part is the object name; earlier parts are folders. Every part is separator-free.
    """
    tid = TenantId.parse(tenant_id)
    if not isinstance(region_code, str) or not _REGION.fullmatch(region_code):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TenantKeyError("region code must be lower-case letters, digits and hyphens")
    key = "/".join(("tenants", str(tid), region_code, *_parts(parts, "object key part")))
    if len(key.encode("utf-8")) > MAX_S3_KEY_BYTES:
        raise TenantKeyError("object key is longer than 1024 bytes")
    return key


def search_index(tenant_id: object, name: str) -> str:
    """Search index name: ``tenant-<id>-<name>`` (name is ``[a-z0-9_]``, so it is unambiguous)."""
    tid = TenantId.parse(tenant_id)
    if not isinstance(name, str) or not _SEARCH_NAME.fullmatch(name):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TenantKeyError("index name must be 1-64 characters of a-z, 0-9 and underscore")
    return f"tenant-{tid}-{name}"


def embedding_namespace(tenant_id: object) -> str:
    """Vector-store namespace: ``tenant:<id>:embedding``."""
    return f"tenant:{TenantId.parse(tenant_id)}:embedding"
