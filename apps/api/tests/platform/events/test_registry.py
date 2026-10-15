"""ARCH-06: the versioned event registry (unit tests, no database).

The registry tracks each event's payload model and owning module, rejects duplicate
``name``+``version`` registrations, validates payloads, cross-checks module manifests against the
models they register, and freezes released schemas against ``packages/contracts/events``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import BaseModel

from aip.platform.events import EventValidationError
from aip.platform.events.registry import (
    CONTRACTS_DIR,
    PLATFORM_EVENT_DEPRECATED,
    DuplicateEventError,
    EventRegistry,
    ManifestEventMismatchError,
    ReleasedSchemaChangedError,
    register_event,
    register_platform_events,
    registry,
    verify_manifest_events,
)


class WidgetCreatedV1(BaseModel):
    widget_id: UUID
    name: str


class WidgetCreatedV1Extra(BaseModel):
    """Same event, same version, but with an extra required field (a forbidden change)."""

    widget_id: UUID
    name: str
    colour: str


# --- registration -------------------------------------------------------------------------------


def test_register_then_schema_for_returns_the_model() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    assert reg.schema_for("widget.created", 1) is WidgetCreatedV1
    assert reg.schema_for("widget.created", 2) is None
    assert reg.schema_for("other.event", 1) is None


def test_registering_the_same_name_and_version_twice_raises_duplicate() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    with pytest.raises(DuplicateEventError) as caught:
        reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    assert caught.value.name == "widget.created" and caught.value.version == 1


def test_a_new_version_of_the_same_event_is_allowed() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    reg.register("widget.created", 2, WidgetCreatedV1Extra, "widgets")
    assert [(s.name, s.version) for s in reg.versions("widget.created")] == [
        ("widget.created", 1),
        ("widget.created", 2),
    ]


def test_specs_are_sorted_by_name_then_version() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 2, WidgetCreatedV1Extra, "widgets")
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    reg.register("alpha.happened", 1, WidgetCreatedV1, "alpha")
    assert [(s.name, s.version) for s in reg.specs()] == [
        ("alpha.happened", 1),
        ("widget.created", 1),
        ("widget.created", 2),
    ]


# --- validation ---------------------------------------------------------------------------------


def test_validate_lists_the_missing_fields() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    with pytest.raises(EventValidationError) as caught:
        reg.validate("widget.created", 1, {})
    assert set(caught.value.fields) == {"widget_id", "name"}
    assert "widget_id" in str(caught.value) and "name" in str(caught.value)


def test_validate_an_unregistered_event_raises() -> None:
    reg = EventRegistry()
    with pytest.raises(EventValidationError, match="no payload model"):
        reg.validate("widget.created", 1, {})


# --- released-schema freeze ---------------------------------------------------------------------


def _write_schema(contracts: Path, name: str, version: int, model: type[BaseModel]) -> None:
    (contracts / f"{name}.v{version}.json").write_text(
        json.dumps(model.model_json_schema(), sort_keys=True), encoding="utf-8"
    )


def test_a_changed_released_payload_raises(tmp_path: Path) -> None:
    # The committed schema is v1 without the extra field; the registered model added one.
    _write_schema(tmp_path, "widget.created", 1, WidgetCreatedV1)
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1Extra, "widgets")
    with pytest.raises(ReleasedSchemaChangedError) as caught:
        reg.verify_released_schemas(tmp_path)
    assert caught.value.name == "widget.created" and caught.value.version == 1


def test_an_unchanged_released_payload_passes(tmp_path: Path) -> None:
    _write_schema(tmp_path, "widget.created", 1, WidgetCreatedV1)
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    reg.verify_released_schemas(tmp_path)  # no file for anything else, so no error


def test_an_event_with_no_committed_file_is_allowed(tmp_path: Path) -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    reg.verify_released_schemas(tmp_path)  # exporter + CI git-diff catch the missing commit


# --- manifest cross-check -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Event:
    name: str
    version: int


@dataclass(frozen=True)
class _Manifest:
    events: list[_Event] = field(default_factory=list)


def _module(module_id: str, events: list[tuple[str, int]]) -> SimpleNamespace:
    return SimpleNamespace(
        id=module_id,
        manifest=_Manifest(events=[_Event(n, v) for n, v in events]),
        package=SimpleNamespace(__name__=f"pkg.{module_id}"),
    )


def test_manifest_and_models_matching_passes() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    verify_manifest_events([_module("widgets", [("widget.created", 1)])], reg)


def test_a_manifest_event_without_a_model_fails() -> None:
    reg = EventRegistry()
    with pytest.raises(ManifestEventMismatchError, match="no model is registered"):
        verify_manifest_events([_module("widgets", [("widget.created", 1)])], reg)


def test_a_model_without_a_manifest_entry_fails() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    with pytest.raises(ManifestEventMismatchError, match="does not declare"):
        verify_manifest_events([_module("widgets", [])], reg)


def test_events_owned_by_a_module_not_in_this_app_are_ignored() -> None:
    reg = EventRegistry()
    reg.register("widget.created", 1, WidgetCreatedV1, "widgets")
    # An app that mounts only "other" must not fail over widgets' event in the shared registry.
    verify_manifest_events([_module("other", [])], reg)


def test_platform_owned_events_need_no_manifest() -> None:
    reg = EventRegistry()
    register_platform_events(reg)
    verify_manifest_events([_module("widgets", [])], reg)
    assert reg.schema_for(PLATFORM_EVENT_DEPRECATED, 1) is not None


def test_register_platform_events_is_idempotent() -> None:
    reg = EventRegistry()
    register_platform_events(reg)
    register_platform_events(reg)  # a second create_app() must not raise
    assert len(reg.versions(PLATFORM_EVENT_DEPRECATED)) == 1


# --- the process-wide registry ------------------------------------------------------------------


def test_register_event_targets_the_global_registry() -> None:
    name = "test_only.registry_probe"
    assert registry.schema_for(name, 1) is None
    register_event(name, 1, WidgetCreatedV1, "widgets")
    try:
        assert registry.schema_for(name, 1) is WidgetCreatedV1
    finally:
        registry._by_key.pop((name, 1), None)  # pyright: ignore[reportPrivateUsage]


def test_contracts_dir_points_at_packages_contracts_events() -> None:
    assert CONTRACTS_DIR.parts[-3:] == ("packages", "contracts", "events")
