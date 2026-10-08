"""Errors raised by the tenant-scoped data access layer (DATABASE-02, ADR 0002)."""

from __future__ import annotations

__all__ = ["DatabaseConfigError", "InvalidTenantError", "TemplateError"]


class InvalidTenantError(ValueError):
    """``with_tenant`` was given something that is not a usable tenant id.

    Raised before any connection is taken from the pool, so a bad tenant never reaches the
    database and never costs a pool checkout.
    """


class DatabaseConfigError(RuntimeError):
    """The application database settings are missing or invalid (``DATABASE_URL``, pool mode)."""


class TemplateError(ValueError):
    """A ``db/templates/*.sql.tpl`` render failed: unknown template, missing or bad variable."""
