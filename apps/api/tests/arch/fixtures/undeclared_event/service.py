"""Fixture: emits an event its manifest does not declare."""

from typing import Any


def emit(conn: Any, name: str, version: int, payload: dict[str, Any]) -> None:
    """Stand-in for the outbox writer."""


def create(conn: Any) -> None:
    emit(conn, "x.y.z", 1, {})
