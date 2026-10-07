#!/usr/bin/env python3
"""Write the FastAPI OpenAPI schema to ``packages/api-client/openapi.json`` (STACK-03).

The output is byte-stable: keys sorted, 2-space indent, UTF-8, one trailing newline. The generated
TypeScript client is built from this file, and ``tools/ci/check_client_drift.sh`` fails CI when it
is out of date.

    uv run python tools/codegen/export_openapi.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "packages" / "api-client" / "openapi.json"


def render() -> str:
    # Import the API from this checkout, ahead of any installed copy of the package.
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from aip.main import create_app
    from aip.platform.modules.registry import DEFAULT_MODULES_PACKAGE

    # A fixed, empty environment so the schema never depends on the caller's settings
    # (e.g. AIP_ENV=test mounts debug routes, though they are excluded from the schema).
    app = create_app(DEFAULT_MODULES_PACKAGE, disabled_modules=(), env="")
    return json.dumps(app.openapi(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output file")
    args = parser.parse_args(argv)
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
