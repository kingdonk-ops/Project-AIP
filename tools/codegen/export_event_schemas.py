#!/usr/bin/env python3
"""Export the event registry's payload schemas to ``packages/contracts/events`` (ARCH-06).

  uv run python tools/codegen/export_event_schemas.py          # rewrite the committed schemas
  uv run python tools/codegen/export_event_schemas.py --check  # exit 1 if any are stale/missing

One file per event version, ``<name>.v<version>.json``, holding ``model_json_schema()`` with
sorted keys and a trailing newline, so two runs are byte-identical. These frozen files back the
boot-time ``ReleasedSchemaChangedError`` check: a released payload may never change in place, only
gain a new version. CI runs ``--check`` and fails on any drift, so a schema change must be
committed together with its version bump.

All modules are loaded (``AIP_DISABLED_MODULES`` is ignored) so the export is the full catalogue,
independent of which modules a given deployment runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "apps" / "api"

sys.path.insert(0, str(API_DIR))

from aip.platform.events.registry import (  # noqa: E402
    CONTRACTS_DIR,
    EventSpec,
    load_module_events,
    register_platform_events,
    registry,
)
from aip.platform.modules.registry import discover  # noqa: E402


def _load_catalogue() -> list[EventSpec]:
    """Populate the process-wide registry from every module plus the platform events."""
    load_module_events(discover())
    register_platform_events(registry)
    return registry.specs()


def _rendered(spec: EventSpec) -> str:
    return json.dumps(spec.json_schema(), indent=2, sort_keys=True) + "\n"


def export(contracts_dir: Path = CONTRACTS_DIR) -> list[Path]:
    """Write every event schema; return the paths written, sorted."""
    contracts_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for spec in _load_catalogue():
        path = contracts_dir / f"{spec.name}.v{spec.version}.json"
        path.write_text(_rendered(spec), encoding="utf-8")
        written.append(path)
    return written


def check(contracts_dir: Path = CONTRACTS_DIR) -> list[str]:
    """Return human-readable drift findings without writing anything."""
    findings: list[str] = []
    specs = _load_catalogue()
    expected = {f"{s.name}.v{s.version}.json" for s in specs}
    for spec in specs:
        path = contracts_dir / f"{spec.name}.v{spec.version}.json"
        if not path.is_file():
            findings.append(f"{path.name}: missing (run export_event_schemas.py)")
        elif path.read_text(encoding="utf-8") != _rendered(spec):
            findings.append(f"{path.name}: out of date (run export_event_schemas.py)")
    if contracts_dir.is_dir():
        for path in sorted(contracts_dir.glob("*.json")):
            if path.name not in expected:
                findings.append(
                    f"{path.name}: no registered event (delete it or restore its model)"
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="fail if the committed schemas drift")
    args = parser.parse_args(argv)
    if args.check:
        findings = check()
        for finding in findings:
            print(finding)
        if findings:
            return 1
        print("export_event_schemas: committed schemas are current")
        return 0
    paths = export()
    print(f"export_event_schemas: wrote {len(paths)} schema(s) to {CONTRACTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
