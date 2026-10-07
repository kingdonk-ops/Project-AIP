"""Fill missing component licences in a Python CycloneDX SBOM from installed package metadata.

Usage: python3 tools/ci/sbom_fill_licences.py <python.cdx.json> <site-packages dir>

`cyclonedx-py environment` reads licence classifiers and `License-Expression`, but drops the
free-text `License:` field. Some packages declare their licence only there (multidict 6.9 has
`License: Apache License 2.0` and no classifier), so their component comes out with no licence
and the policy check denies it as unknown.

For each component that has NO licence, this copies the package's own `License:` value into the
SBOM as a declared licence *name*. It never overwrites an existing licence and never invents
one: a package without a short `License:` value stays unknown and is still denied. The policy
check (check_licences.py) then judges the name through its alias table, so an unrecognised name
is denied too. Stdlib only (STACK-04).
"""

from __future__ import annotations

import json
import re
import sys
from email.parser import HeaderParser
from pathlib import Path

# A licence *name* is short; longer values are usually the whole licence text pasted in.
MAX_NAME_LENGTH = 80


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_licences(site_packages: Path) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for metadata in site_packages.glob("*.dist-info/METADATA"):
        headers = HeaderParser().parsestr(metadata.read_text(encoding="utf-8", errors="replace"))
        name, version, licence = headers.get("Name"), headers.get("Version"), headers.get("License")
        if not (name and version and licence):
            continue
        licence = licence.strip()
        if licence and "\n" not in licence and len(licence) <= MAX_NAME_LENGTH:
            found[(_normalise(name), version.strip())] = licence
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    sbom_path, site_packages = Path(argv[1]), Path(argv[2])
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    declared = _declared_licences(site_packages)
    for component in sbom.get("components", []):
        if component.get("licenses"):
            continue
        key = (_normalise(str(component.get("name", ""))), str(component.get("version", "")))
        licence = declared.get(key)
        if licence is None:
            continue
        component["licenses"] = [{"license": {"name": licence, "acknowledgement": "declared"}}]
        print(f"sbom: filled {key[0]}@{key[1]} licence from METADATA License: {licence!r}")
    sbom_path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
