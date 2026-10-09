"""Smoke test: the tenancy module imports, its manifest validates, api exports its names."""

import importlib
from pathlib import Path

from aip.platform.modules.manifest import ModuleManifest

MODULE_DIR = Path(__file__).resolve().parents[1]


def test_module_imports_and_manifest_validates() -> None:
    module = importlib.import_module(f"aip.modules.{MODULE_DIR.name}")
    assert module.__all__ == ["api"]

    manifest = ModuleManifest.from_toml(MODULE_DIR / "manifest.toml")
    assert manifest.id == "tenancy"


def test_api_exports_only_the_published_interface() -> None:
    api = importlib.import_module("aip.modules.tenancy.api")
    assert sorted(api.__all__) == [
        "Denial",
        "TenantView",
        "access_for_status",
        "get_tenant",
        "load_tenant",
        "require_active_tenant",
    ]
