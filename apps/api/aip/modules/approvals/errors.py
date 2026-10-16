"""Errors raised by the approvals module (APPROVALS-01)."""

from __future__ import annotations

__all__ = ["DefinitionImmutableError", "DefinitionNotFoundError", "NoActiveDefinitionError"]


class DefinitionImmutableError(Exception):
    """Only a ``draft`` definition can be edited or published; active and retired ones are fixed."""


class DefinitionNotFoundError(LookupError):
    """No live definition with that id in this tenant."""


class NoActiveDefinitionError(LookupError):
    """Neither a project-specific nor a tenant-wide active definition exists for a record type."""
