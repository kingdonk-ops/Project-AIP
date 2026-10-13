"""Where ``emit`` finds the payload model for an event name and version (ARCH-05).

``EventSchemaLookup`` is the seam: ARCH-06 supplies the versioned event registry. Until then
``DictEventSchemaLookup`` holds the models that modules register at import time.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel

__all__ = ["DictEventSchemaLookup", "EventSchemaLookup"]


class EventSchemaLookup(Protocol):
    def schema_for(self, event_name: str, version: int) -> type[BaseModel] | None:
        """The payload model of ``event_name`` at ``version``, or ``None`` if unknown."""
        ...


class DictEventSchemaLookup:
    """An ``EventSchemaLookup`` backed by a dict keyed by ``(event_name, version)``."""

    __slots__ = ("_schemas",)

    def __init__(self, schemas: Mapping[tuple[str, int], type[BaseModel]] | None = None) -> None:
        self._schemas: dict[tuple[str, int], type[BaseModel]] = dict(schemas or {})

    def register(self, event_name: str, version: int, model: type[BaseModel]) -> None:
        """Add a payload model. Registering a different model for the same key is an error."""
        key = (event_name, version)
        existing = self._schemas.get(key)
        if existing is not None and existing is not model:
            raise ValueError(f"{event_name} v{version} is already registered")
        self._schemas[key] = model

    def schema_for(self, event_name: str, version: int) -> type[BaseModel] | None:
        return self._schemas.get((event_name, version))
