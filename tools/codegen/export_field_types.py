#!/usr/bin/env python3
"""Write the shared field-type registry to ``packages/contracts/field-types/field-types.json``.

The TypeScript form renderer and type editor read this contract; the backend registry
(``aip.modules.item_types.field_types``) is the source of truth. The output is byte-stable (keys
sorted, 2-space indent, UTF-8, one trailing newline) and a test fails when the committed file is
out of date (ITEMTYPES-01).

    uv run python tools/codegen/export_field_types.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "packages" / "contracts" / "field-types" / "field-types.json"


def payload() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    from aip.modules.item_types.field_types import field_types

    return {
        "version": 1,
        "fieldTypes": [
            {
                "key": field.key,
                "termKey": field.term_key,
                "usableIn": sorted(field.usable_in),
                "configSchema": field.config_schema,
            }
            for field in field_types()
        ],
    }


def render() -> str:
    return json.dumps(payload(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the shared field-type registry.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output file")
    args = parser.parse_args(argv)
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
