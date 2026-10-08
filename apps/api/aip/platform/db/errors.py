"""Errors raised by the tenant-scoped data access layer (DATABASE-02, ADR 0002)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "ConflictError",
    "CycleError",
    "DatabaseConfigError",
    "InvalidSchemaError",
    "InvalidTenantError",
    "NotFoundError",
    "TemplateError",
]


class InvalidTenantError(ValueError):
    """``with_tenant`` was given something that is not a usable tenant id.

    Raised before any connection is taken from the pool, so a bad tenant never reaches the
    database and never costs a pool checkout.
    """


class DatabaseConfigError(RuntimeError):
    """The application database settings are missing or invalid (``DATABASE_URL``, pool mode)."""


class TemplateError(ValueError):
    """A ``db/templates/*.sql.tpl`` render failed: unknown template, missing or bad variable."""


class ConflictError(Exception):
    """An optimistic-concurrency update used a stale ``sync_version`` (HTTP 409 VERSION_CONFLICT).

    ``current`` is the row as it is stored now, so the client can show a field diff.
    """

    def __init__(self, current: Mapping[str, Any]) -> None:
        super().__init__("version conflict: the record changed since it was read")
        self.current = dict(current)


class NotFoundError(LookupError):
    """No live (not soft-deleted) row matches, in this tenant (HTTP 404)."""


class CycleError(ValueError):
    """A subtree move would put a node under itself or one of its own descendants."""


class InvalidSchemaError(ValueError):
    """A stored per-type JSON Schema is itself not a valid Draft 2020-12 schema."""
