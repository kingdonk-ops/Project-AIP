#!/usr/bin/env python3
"""Check each module's manifest declares what its code uses (ARCH-03). Stdlib only.

For every module directory (one holding a ``manifest.toml``) this parses the module's Python files
with ``ast`` and collects string-literal arguments of:

- ``require_permission("<code>", ...)``: first argument, must be in ``permissions``;
- ``emit(conn, "<event>", <version>, ...)``: second argument, must be in ``events`` (by name);
- ``term("<key>", ...)``: first argument, must be in ``term_keys``.

Calls may be plain (``emit(...)``) or attribute calls (``outbox.emit(...)``). Non-literal arguments
cannot be checked statically and are skipped. Module ``tests/`` folders and modules whose name
starts with ``_`` (the scaffolding template) are skipped.

Prints one line per missing item and exits 1 if there are any.
Usage: python3 tools/ci/check_manifests.py [MODULES_DIR_OR_MODULE ...]
(default: apps/api/aip/modules)
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("apps/api/aip/modules")

# call name -> (argument index, manifest key)
CHECKED_CALLS: dict[str, tuple[int, str]] = {
    "require_permission": (0, "permissions"),
    "emit": (1, "events"),
    "term": (0, "term_keys"),
}


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def used_items(source: str, filename: str) -> list[tuple[str, str, int]]:
    """Return ``(manifest_key, value, line)`` for each checked call with a literal argument."""
    found: list[tuple[str, str, int]] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in CHECKED_CALLS:
            continue
        index, key = CHECKED_CALLS[name]
        if len(node.args) <= index:
            continue
        arg = node.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.append((key, arg.value, node.lineno))
    return found


def _declared(manifest: dict[str, Any]) -> dict[str, set[str]]:
    events: set[str] = set()
    for event in manifest.get("events", []):
        if isinstance(event, dict) and isinstance(event.get("name"), str):
            events.add(event["name"])  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(event, str):
            events.add(event)
    return {
        "permissions": {str(p) for p in manifest.get("permissions", [])},
        "events": events,
        "term_keys": {str(t) for t in manifest.get("term_keys", [])},
    }


def _python_files(module_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in module_dir.rglob("*.py")
        if "tests" not in p.relative_to(module_dir).parts[:-1]
        and "__pycache__" not in p.relative_to(module_dir).parts
    )


def check_module(module_dir: Path) -> list[str]:
    """Return one error line per item used in the module's code but missing from its manifest."""
    manifest_path = module_dir / "manifest.toml"
    if not manifest_path.is_file():
        return [f"{module_dir}: no manifest.toml"]
    try:
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return [f"{manifest_path}: cannot parse: {exc}"]
    declared = _declared(manifest)

    errors: list[str] = []
    for path in _python_files(module_dir):
        try:
            items = used_items(path.read_text(encoding="utf-8"), str(path))
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: syntax error, cannot check: {exc}")
            continue
        for key, value, line in items:
            if value not in declared[key]:
                errors.append(
                    f"{path}:{line}: '{value}' is used but not declared in {manifest_path} [{key}]"
                )
    return errors


def _module_dirs(root: Path) -> list[Path]:
    if (root / "manifest.toml").is_file():
        return [root]
    return sorted(
        d
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(("_", ".")) and d.name != "__pycache__"
    )


def check_manifests(root: Path) -> list[str]:
    """Check one module directory, or every module directory under ``root``."""
    root = Path(root)
    if root.name.startswith("_") and not (root / "manifest.toml").is_file():
        return []
    errors: list[str] = []
    for module_dir in _module_dirs(root):
        errors.extend(check_module(module_dir))
    return errors


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv] or [DEFAULT_ROOT]
    errors: list[str] = []
    for root in roots:
        if not root.is_dir():
            errors.append(f"{root}: not a directory")
            continue
        errors.extend(check_manifests(root))
    for error in errors:
        print(error)
    if errors:
        return 1
    print("check_manifests: all module manifests declare what their code uses")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
