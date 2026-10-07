#!/usr/bin/env python3
"""Scaffold a backend module from ``apps/api/aip/modules/_template`` (ARCH-01, ADR 0004).

  python tools/new_module.py <name>

``<name>`` must be a snake_case Python package name (``^[a-z][a-z0-9_]*$``). The template is
copied to a hidden staging folder, ``__module__`` is substituted, and the generated manifest is
validated. Only then is the folder renamed into place, so a failure leaves nothing behind and
never touches anything that existed before.
"""

from __future__ import annotations

import keyword
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "apps" / "api"
MODULES_DIR = API_DIR / "aip" / "modules"
TEMPLATE_DIR = MODULES_DIR / "_template"
PLACEHOLDER = "__module__"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# Names that would shadow package internals or test discovery.
RESERVED_NAMES = frozenset({"tests", "platform", "shared", "modules", "main", "worker"})
_REEXEC_ENV = "AIP_NEW_MODULE_REEXEC"


class ScaffoldError(Exception):
    """A user-facing failure; the message is printed and the exit code is 1."""


def validate_name(name: str) -> None:
    if not NAME_RE.fullmatch(name):
        raise ScaffoldError(
            f"invalid module name {name!r}: use snake_case matching {NAME_RE.pattern}"
        )
    if keyword.iskeyword(name) or name in RESERVED_NAMES:
        raise ScaffoldError(f"module name {name!r} is reserved; choose another name")


def _load_manifest_class() -> type:
    sys.path.insert(0, str(API_DIR))
    from aip.platform.modules.manifest import ModuleManifest

    return ModuleManifest


def ensure_dependencies() -> None:
    """Re-run under ``uv run`` when invoked by an interpreter without the API's dependencies."""
    try:
        import pydantic  # noqa: F401  # pyright: ignore[reportUnusedImport]
    except ImportError:
        uv = shutil.which("uv")
        if uv is None or os.environ.get(_REEXEC_ENV):
            raise ScaffoldError(
                "pydantic is not installed; run `uv sync --all-packages --frozen` first"
            ) from None
        env = {**os.environ, _REEXEC_ENV: "1"}
        script = str(Path(__file__).resolve())
        cmd = [uv, "run", "--frozen", "--project", str(ROOT), "python", script, *sys.argv[1:]]
        sys.exit(subprocess.call(cmd, env=env))


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in {"__pycache__", ".pytest_cache"} or n.endswith(".pyc")}


def scaffold(name: str) -> Path:
    validate_name(name)
    target = MODULES_DIR / name
    if target.exists() or target.is_symlink():
        raise ScaffoldError(f"module {name} already exists")
    if not TEMPLATE_DIR.is_dir():
        raise ScaffoldError(f"template not found at {TEMPLATE_DIR}")

    ensure_dependencies()
    manifest_cls = _load_manifest_class()

    staging = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=MODULES_DIR))
    try:
        build = staging / name
        shutil.copytree(TEMPLATE_DIR, build, ignore=_ignore)
        for path in build.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                if PLACEHOLDER in text:
                    path.write_text(text.replace(PLACEHOLDER, name), encoding="utf-8")

        try:
            manifest = manifest_cls.from_toml(build / "manifest.toml")
        except Exception as exc:
            raise ScaffoldError(f"generated manifest is invalid: {exc}") from exc
        if manifest.id != name:
            raise ScaffoldError(f"generated manifest id {manifest.id!r} != {name!r}")

        try:
            # Atomic on the same filesystem; fails if the target appeared meanwhile.
            os.rename(build, target)
        except OSError as exc:
            if target.exists():
                raise ScaffoldError(f"module {name} already exists") from exc
            raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python tools/new_module.py <snake_case_name>", file=sys.stderr)
        return 2
    try:
        target = scaffold(argv[0])
    except ScaffoldError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
