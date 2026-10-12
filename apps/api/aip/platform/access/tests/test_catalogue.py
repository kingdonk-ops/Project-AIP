"""Permission catalogue validation (ACCESS-01 step 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aip.platform.access import CatalogueError, build_catalogue, load_manifests
from aip.platform.modules.manifest import ModuleManifest


def manifest(module_id: str, *codes: str, **extra: Any) -> ModuleManifest:
    return ModuleManifest.model_validate(
        {
            "id": module_id,
            "context": "test",
            "permissions": [{"code": c, "description": f"{c} description"} for c in codes],
            **extra,
        }
    )


def test_catalogue_is_sorted_and_keeps_flags() -> None:
    m = ModuleManifest.model_validate(
        {
            "id": "assets",
            "context": "test",
            "permissions": [
                {"code": "assets.asset.update", "description": "Edit", "privileged": True},
                {"code": "assets.asset.read", "description": "View"},
            ],
        }
    )
    catalogue = build_catalogue([m])
    assert list(catalogue) == ["assets.asset.read", "assets.asset.update"]
    assert catalogue["assets.asset.update"].privileged
    assert catalogue["assets.asset.read"].module_id == "assets"
    assert catalogue.sync_payload()[0] == {
        "code": "assets.asset.read",
        "module_id": "assets",
        "description": "View",
        "is_privileged": False,
    }


@pytest.mark.parametrize(
    "code",
    ["Assets.Read", "assets", "assets.a.b.c", "assets..read", "assets.Read", "1assets.read"],
)
def test_invalid_code_fails_naming_the_module(code: str) -> None:
    with pytest.raises(CatalogueError) as exc:
        build_catalogue([manifest("assets", code)])
    assert "module assets" in str(exc.value)
    assert code in str(exc.value)


def test_two_and_three_segment_codes_are_valid() -> None:
    catalogue = build_catalogue([manifest("audit", "audit.view", "audit.activity.view")])
    assert set(catalogue) == {"audit.view", "audit.activity.view"}


def test_code_outside_the_module_namespace_fails() -> None:
    with pytest.raises(CatalogueError, match=r"module assets: permission project\.view"):
        build_catalogue([manifest("assets", "project.view")])


def test_declared_namespaces_replace_the_default() -> None:
    m = manifest("projects", "project.view", "site.view", permission_namespaces=["project", "site"])
    assert set(build_catalogue([m])) == {"project.view", "site.view"}


def test_namespace_claimed_by_two_modules_fails() -> None:
    a = manifest("projects", permission_namespaces=["project"])
    b = manifest("sites", permission_namespaces=["project", "sites"])
    with pytest.raises(
        CatalogueError, match="namespace project is claimed by modules projects and sites"
    ):
        build_catalogue([a, b])


def test_duplicate_code_fails() -> None:
    with pytest.raises(CatalogueError, match=r"duplicate permission fixture\.item\.read"):
        build_catalogue([manifest("fixture", "fixture.item.read", "fixture.item.read")])


def test_coarse_write_permission_fails() -> None:
    with pytest.raises(CatalogueError, match="coarse"):
        build_catalogue([manifest("inspections", "inspections.inspection.write")])


def test_load_manifests_reads_toml_and_skips_private_folders(tmp_path: Path) -> None:
    for name in ("b_mod", "a_mod", "_template", ".hidden"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "manifest.toml").write_text(f'id = "{name.strip("._")}"\ncontext = "x"\n')
    (tmp_path / "no_manifest").mkdir()
    assert [m.id for m in load_manifests(tmp_path)] == ["a_mod", "b_mod"]


def test_the_real_modules_build_a_catalogue() -> None:
    modules_dir = Path(__file__).resolve().parents[3] / "modules"  # aip/modules, not imported
    catalogue = build_catalogue(load_manifests(modules_dir))
    assert "access.role.manage" in catalogue
    assert catalogue["access.role.manage"].privileged
