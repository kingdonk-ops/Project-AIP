"""Domain events platform service (ARCH-05, ADR 0003): the ``domain_events`` outbox.

- ``outbox``: ``emit(conn, ...)`` writes an event in the caller's ``with_tenant`` transaction.
- ``lookup``: ``EventSchemaLookup``, where ``emit`` finds each event's payload model.
- ``tables``: the SQLAlchemy Core ``domain_events`` table.
"""

from aip.platform.events.lookup import DictEventSchemaLookup, EventSchemaLookup
from aip.platform.events.outbox import Aggregate, EventValidationError, emit, event_schemas

__all__ = [
    "Aggregate",
    "DictEventSchemaLookup",
    "EventSchemaLookup",
    "EventValidationError",
    "emit",
    "event_schemas",
]
