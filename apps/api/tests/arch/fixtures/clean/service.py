"""Fixture: uses only declared permissions, events and term keys."""

from typing import Any


def require_permission(code: str) -> None:
    """Stand-in for the policy dependency."""


def emit(conn: Any, name: str, version: int, payload: dict[str, Any]) -> None:
    """Stand-in for the outbox writer."""


def term(key: str) -> str:
    """Stand-in for the terminology lookup."""
    return key


def create(conn: Any, name: str) -> str:
    require_permission("clean.widget.read")
    emit(conn, "clean.widget.created", 1, {"name": name})
    # Non-literal arguments cannot be checked statically and are skipped.
    emit(conn, name, 1, {})
    return term("clean.widget.label")
