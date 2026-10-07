"""Smoke test: the __module__ module imports and its manifest validates."""

import importlib
from pathlib import Path

from aip.platform.modules.manifest import ModuleManifest

MODULE_DIR = Path(__file__).resolve().parents[1]


def test_module_imports_and_manifest_validates() -> None:
    module = importlib.import_module(f"aip.modules.{MODULE_DIR.name}")
    assert module.__all__ == ["api"]

    manifest = ModuleManifest.from_toml(MODULE_DIR / "manifest.toml")
    assert manifest.id == "__module__"
