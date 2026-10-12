from pathlib import Path

import pytest
from pydantic import ValidationError

from aip.platform.modules.manifest import EventRef, ModuleManifest, PermissionEntry

MINIMAL = {"id": "x", "context": "platform", "depends_on": [], "events": []}


def test_empty_manifest_reports_missing_id() -> None:
    with pytest.raises(ValidationError) as exc:
        ModuleManifest.model_validate({})
    assert any(err["loc"] == ("id",) for err in exc.value.errors())


def test_minimal_manifest_validates() -> None:
    manifest = ModuleManifest.model_validate(MINIMAL)
    assert manifest.id == "x"
    assert manifest.permissions == []
    assert manifest.subscribes == []
    assert manifest.settings == []
    assert manifest.term_keys == []


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        ModuleManifest.model_validate({**MINIMAL, "colour": "red"})


@pytest.mark.parametrize("bad_id", ["Bad Name", "widgets-x", "1abc", "Widgets", ""])
def test_id_must_be_snake_case(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        ModuleManifest.model_validate({**MINIMAL, "id": bad_id})


def test_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "manifest.toml"
    path.write_text(
        'id = "widgets"\n'
        'context = "test"\n'
        "depends_on = []\n"
        'events = [{ name = "widget.created", version = 1 }]\n'
        "[[permissions]]\n"
        'code = "widgets.widget.read"\n'
        'description = "View widgets"\n'
    )
    manifest = ModuleManifest.from_toml(path)
    assert manifest.id == "widgets"
    assert manifest.events == [EventRef(name="widget.created", version=1)]
    assert manifest.permissions == [
        PermissionEntry(code="widgets.widget.read", description="View widgets", privileged=False)
    ]
    assert manifest.namespaces == ("widgets",)


def test_permission_namespaces_default_to_the_module_id() -> None:
    manifest = ModuleManifest.model_validate({**MINIMAL, "permission_namespaces": ["x", "y"]})
    assert manifest.namespaces == ("x", "y")


def test_permission_entry_needs_a_description() -> None:
    with pytest.raises(ValidationError):
        ModuleManifest.model_validate({**MINIMAL, "permissions": [{"code": "x.thing.read"}]})


def test_plain_string_permissions_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ModuleManifest.model_validate({**MINIMAL, "permissions": ["x.thing.read"]})
