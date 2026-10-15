"""Domain events platform service (ARCH-05/ARCH-06, ADR 0003): the ``domain_events`` outbox and
the versioned event registry.

- ``outbox``: ``emit(conn, ...)`` writes an event in the caller's ``with_tenant`` transaction.
- ``lookup``: ``EventSchemaLookup``, the seam ``emit`` uses to find each event's payload model.
- ``registry``: the process-wide :class:`EventRegistry`; modules register their events here with
  ``register_event`` and ``emit`` validates against it.
- ``tables``: the SQLAlchemy Core ``domain_events`` table.
"""

from aip.platform.events.lookup import DictEventSchemaLookup, EventSchemaLookup
from aip.platform.events.outbox import Aggregate, EventValidationError, emit
from aip.platform.events.registry import (
    DuplicateEventError,
    EventRegistry,
    EventSpec,
    ReleasedSchemaChangedError,
    register_event,
    registry,
)

__all__ = [
    "Aggregate",
    "DictEventSchemaLookup",
    "DuplicateEventError",
    "EventRegistry",
    "EventSchemaLookup",
    "EventSpec",
    "EventValidationError",
    "ReleasedSchemaChangedError",
    "emit",
    "register_event",
    "registry",
]
