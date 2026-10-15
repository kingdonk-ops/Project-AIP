"""Versioned event registry and catalogue (ARCH-06).

The registry is the single source of truth for the domain events the process knows about: each
event's payload model, the module that owns it and its released JSON Schema. It is an
:class:`~aip.platform.events.lookup.EventSchemaLookup`, so ``emit`` (ARCH-05) finds payload models
here.

Registration happens at import time. Every module's ``events.py`` calls
``register_event(name, version, model, owner)``; the module registry (ARCH-02) imports those
files at boot (:func:`load_module_events`). Platform-owned events (the catalogue's own
``platform.event.deprecated``) are registered by :func:`register_platform_events`.

Three integrity rules, checked at boot and in CI:

- a ``name``+``version`` may be registered once (:class:`DuplicateEventError`);
- a module's manifest ``events`` and the events it registers must match exactly
  (:func:`verify_manifest_events`), so a manifest entry without a model, or a model without a
  manifest entry, fails boot;
- a registered model whose schema differs from the committed
  ``packages/contracts/events/<name>.v<version>.json`` raises :class:`ReleasedSchemaChangedError`
  (:func:`verify_released_schemas`): a payload change needs a new version. ``export_event_schemas``
  writes those files and CI fails on any ``git diff``.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

from aip.platform.events.outbox import EventValidationError

__all__ = [
    "CONTRACTS_DIR",
    "PLATFORM_EVENT_DEPRECATED",
    "PLATFORM_OWNER",
    "DuplicateEventError",
    "EventDeprecatedPayload",
    "EventRegistry",
    "EventSpec",
    "ReleasedSchemaChangedError",
    "load_module_events",
    "register_event",
    "register_platform_events",
    "registry",
    "verify_manifest_events",
    "verify_released_schemas",
]

# packages/contracts/events, relative to the repo root (apps/api/aip/platform/events/registry.py).
CONTRACTS_DIR = Path(__file__).resolve().parents[5] / "packages" / "contracts" / "events"

PLATFORM_OWNER = "platform"
PLATFORM_EVENT_DEPRECATED = "platform.event.deprecated"


class DuplicateEventError(ValueError):
    """A ``name``+``version`` is registered more than once."""

    def __init__(self, name: str, version: int, owner: str, existing_owner: str) -> None:
        self.name = name
        self.version = version
        super().__init__(
            f"event {name} v{version} is already registered (by {existing_owner}); "
            f"{owner} cannot register it again"
        )


class ReleasedSchemaChangedError(Exception):
    """A registered model no longer matches its committed JSON Schema (bump the version)."""

    def __init__(self, name: str, version: int) -> None:
        self.name = name
        self.version = version
        super().__init__(
            f"the payload of {name} v{version} differs from its released schema in "
            f"packages/contracts/events/{name}.v{version}.json; a payload change needs a new "
            "version (register v{next}), never an edit to a released one"
        )


class ManifestEventMismatchError(Exception):
    """A module's manifest ``events`` and its registered models disagree."""


@dataclass(frozen=True, slots=True)
class EventSpec:
    """One registered event: its payload model and the module that owns it."""

    name: str
    version: int
    owner: str
    model: type[BaseModel]

    def json_schema(self) -> dict[str, Any]:
        """The payload JSON Schema with sorted keys, as committed to ``packages/contracts``."""
        return _sorted(self.model.model_json_schema())


def _sorted(value: Any) -> Any:
    """Recursively sort mapping keys so the exported schema is byte-stable."""
    if isinstance(value, dict):
        mapping = cast("dict[str, Any]", value)
        return {key: _sorted(mapping[key]) for key in sorted(mapping)}
    if isinstance(value, list):
        items = cast("list[Any]", value)
        return [_sorted(item) for item in items]
    return value


class EventRegistry:
    """The process-wide event catalogue; an ``EventSchemaLookup`` for ``emit``."""

    __slots__ = ("_by_key",)

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, int], EventSpec] = {}

    def register(self, name: str, version: int, model: type[BaseModel], owner: str) -> None:
        """Register ``name`` v``version``'s payload ``model`` for module ``owner``.

        Raises :class:`DuplicateEventError` if the ``name``+``version`` is already registered.
        """
        if not name or version < 1 or not owner:
            raise ValueError(f"invalid event registration {name!r} v{version} owner {owner!r}")
        key = (name, version)
        existing = self._by_key.get(key)
        if existing is not None:
            raise DuplicateEventError(name, version, owner, existing.owner)
        self._by_key[key] = EventSpec(name=name, version=version, owner=owner, model=model)

    def schema_for(self, event_name: str, version: int) -> type[BaseModel] | None:
        """The payload model of ``event_name`` at ``version`` (``EventSchemaLookup``)."""
        spec = self._by_key.get((event_name, version))
        return spec.model if spec is not None else None

    def validate(self, event_name: str, version: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate ``payload`` against the registered model; raise ``EventValidationError``."""
        model = self.schema_for(event_name, version)
        if model is None:
            raise EventValidationError(event_name, version, (), "no payload model is registered")
        try:
            return model.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            fields = tuple(dict.fromkeys(".".join(str(p) for p in e["loc"]) for e in exc.errors()))
            raise EventValidationError(
                event_name, version, fields, f"invalid payload fields: {', '.join(fields)}"
            ) from None

    def specs(self) -> list[EventSpec]:
        """Every registered event, sorted by name then version."""
        return [self._by_key[key] for key in sorted(self._by_key)]

    def spec(self, name: str, version: int) -> EventSpec | None:
        return self._by_key.get((name, version))

    def versions(self, name: str) -> list[EventSpec]:
        """Every registered version of ``name``, ascending."""
        return [s for s in self.specs() if s.name == name]

    def verify_released_schemas(self, contracts_dir: Path = CONTRACTS_DIR) -> None:
        """Raise :class:`ReleasedSchemaChangedError` for any model that drifted from its file.

        An event with no committed file yet is allowed (the exporter writes it and CI's
        ``git diff`` catches the missing commit); only a *changed* released schema fails.
        """
        for spec in self.specs():
            path = contracts_dir / f"{spec.name}.v{spec.version}.json"
            if not path.is_file():
                continue
            committed = json.loads(path.read_text(encoding="utf-8"))
            if committed != spec.json_schema():
                raise ReleasedSchemaChangedError(spec.name, spec.version)


registry = EventRegistry()
"""The process-wide registry. ``emit`` defaults to it; modules register into it at import."""


def register_event(name: str, version: int, model: type[BaseModel], owner: str) -> None:
    """Register an event in the process-wide :data:`registry` (see ``EventRegistry.register``)."""
    registry.register(name, version, model, owner)


class EventDeprecatedPayload(BaseModel):
    """Payload of ``platform.event.deprecated`` v1 (emitted when an operator deprecates it)."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True, extra="forbid"
    )

    event_name: str
    event_version: int
    deprecated_by: UUID | None = None


def register_platform_events(reg: EventRegistry = registry) -> None:
    """Register the catalogue's own platform-owned events (idempotent across ``create_app``)."""
    if reg.spec(PLATFORM_EVENT_DEPRECATED, 1) is None:
        reg.register(PLATFORM_EVENT_DEPRECATED, 1, EventDeprecatedPayload, PLATFORM_OWNER)


def verify_released_schemas(
    reg: EventRegistry = registry, contracts_dir: Path = CONTRACTS_DIR
) -> None:
    """Module-level wrapper over :meth:`EventRegistry.verify_released_schemas`."""
    reg.verify_released_schemas(contracts_dir)


def load_module_events(modules: Iterable[Any]) -> None:
    """Import every module's ``events.py`` so its ``register_event`` calls run (ARCH-02 boot).

    ``modules`` are ``LoadedModule``s. A module with no ``events.py`` is fine; any other import
    error propagates (a broken events module must stop the process).
    """
    for module in modules:
        package = module.package.__name__
        try:
            importlib.import_module(f"{package}.events")
        except ModuleNotFoundError as exc:
            if exc.name != f"{package}.events":
                raise  # a real missing import inside events.py, not a missing events.py


def verify_manifest_events(modules: Iterable[Any], reg: EventRegistry = registry) -> None:
    """Fail boot unless each module's manifest ``events`` exactly matches what it registered.

    Only events owned by a module in ``modules`` are considered: the process-wide registry may
    carry events from modules this app does not mount (another ``create_app`` configuration, or a
    service imported in the same process), and platform-owned events have no manifest. So a module
    is checked against the events it owns, and nothing else can make its check fail.
    """
    modules = list(modules)
    module_ids = {module.id for module in modules}
    registered: dict[str, set[tuple[str, int]]] = {}
    for spec in reg.specs():
        if spec.owner in module_ids:
            registered.setdefault(spec.owner, set()).add((spec.name, spec.version))

    for module in modules:
        declared = {(e.name, e.version) for e in module.manifest.events}
        found = registered.get(module.id, set())
        missing_model = declared - found
        if missing_model:
            listed = ", ".join(f"{n} v{v}" for n, v in sorted(missing_model))
            raise ManifestEventMismatchError(
                f"module {module.id}: manifest declares {listed} but no model is registered "
                "(its events.py must register_event them)"
            )
        missing_manifest = found - declared
        if missing_manifest:
            listed = ", ".join(f"{n} v{v}" for n, v in sorted(missing_manifest))
            raise ManifestEventMismatchError(
                f"module {module.id}: registers {listed} but its manifest does not declare them"
            )
