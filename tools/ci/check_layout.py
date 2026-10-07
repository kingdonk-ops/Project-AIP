#!/usr/bin/env python3
"""Check the repository keeps the ADR 0004 layout (ARCH-03). Stdlib only.

Fails on:
- any top-level ``backend/``, ``frontend/`` or ``services/`` path;
- any TypeScript file (``.ts``, ``.tsx``, ``.mts``, ``.cts``) or ``package.json`` under
  ``apps/api/``;
- any ``*.py`` file under ``packages/`` (the TypeScript workspace).

Checks the files git knows about (tracked plus untracked, not ignored). Prints one line per
offending path and exits 1 if there are any.
Usage: python3 tools/ci/check_layout.py
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from pathlib import PurePosixPath

FORBIDDEN_TOP_LEVEL = ("backend", "frontend", "services")
TS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts")


def check_path(path: str) -> str | None:
    """Return an error for one repo-relative path, or ``None`` if it is allowed."""
    parts = PurePosixPath(path).parts
    if not parts:
        return None
    if parts[0] in FORBIDDEN_TOP_LEVEL:
        return f"{path}: top-level {parts[0]}/ is not part of the ADR 0004 layout"
    if parts[:2] == ("apps", "api"):
        if path.endswith(TS_SUFFIXES):
            return f"{path}: no TypeScript under apps/api/ (ADR 0004)"
        if parts[-1] == "package.json":
            return f"{path}: no package.json under apps/api/ (ADR 0004)"
    if parts[0] == "packages" and path.endswith(".py"):
        return f"{path}: no Python under packages/ (ADR 0004)"
    return None


def check_layout(paths: Iterable[str]) -> list[str]:
    """Return one error per path that breaks the layout, in input order."""
    return [error for path in paths if (error := check_path(path)) is not None]


def _git_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> int:
    errors = check_layout(_git_files())
    for error in errors:
        print(error)
    if errors:
        return 1
    print("check_layout: repository layout matches ADR 0004")
    return 0


if __name__ == "__main__":
    sys.exit(main())
