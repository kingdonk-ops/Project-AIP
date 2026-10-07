#!/usr/bin/env python3
"""Lint the ADR record so it cannot drift (STACK-01). Stdlib only.

Checks:
- every docs/adr/NNNN-*.md (except 0000-template.md) has a unique number and a Status
  and a Date bullet;
- every `- **Supersedes:** NNNN` target exists;
- every ADR file is listed in docs/adr/README.md;
- docs/blueprint/01-decisions.md still carries the errata marker (a blueprint regeneration
  drops it);
- the Python and Node rows of docs/stack/versions.md match .python-version and .nvmrc.

Prints one line per finding and exits 1 if there are any.
Usage: python3 tools/ci/check_adrs.py [--root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ERRATA_MARKER = "<!-- errata: keep on regeneration -->"
ADR_FILE = re.compile(r"^(\d{4})-[^/]+\.md$")
BULLET = re.compile(r"^- \*\*(Status|Date|Supersedes):\*\*\s*(.*?)\s*$")
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})\b")
ADR_NUMBER = re.compile(r"\b(\d{4})\b")

Header = dict[str, int | str | list[int] | None]


def parse_adr_header(filename: str, text: str) -> Header:
    """Return {number, status, date, supersedes} from an ADR's filename and header bullets."""
    match = ADR_FILE.match(filename)
    header: Header = {
        "number": int(match.group(1)) if match else None,
        "status": None,
        "date": None,
        "supersedes": None,
    }
    for line in text.splitlines():
        bullet = BULLET.match(line)
        if not bullet:
            continue
        key, value = bullet.group(1), bullet.group(2)
        if key == "Status" and header["status"] is None and value:
            header["status"] = value
        elif key == "Date" and header["date"] is None:
            date = DATE.match(value)
            header["date"] = date.group(1) if date else None
        elif key == "Supersedes" and header["supersedes"] is None:
            numbers = [int(n) for n in ADR_NUMBER.findall(value)]
            header["supersedes"] = numbers or None
    return header


def parse_versions_table(text: str) -> dict[str, str]:
    """Map Component -> Version from the `| Component | Version | ... |` table rows."""
    versions: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0] == "Component":
            continue
        versions[cells[0].strip("`")] = cells[1].strip("`")
    return versions


def check_adrs(root: Path) -> list[str]:
    findings: list[str] = []
    adr_dir = root / "docs" / "adr"
    index_path = adr_dir / "README.md"
    index = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    if not index:
        findings.append("docs/adr/README.md is missing")

    headers: dict[int, Header] = {}
    for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        if path.name == "0000-template.md":
            continue
        header = parse_adr_header(path.name, path.read_text(encoding="utf-8"))
        number = header["number"]
        assert isinstance(number, int)
        label = f"{number:04d}"
        if number in headers:
            findings.append(f"duplicate ADR number {label}")
        else:
            headers[number] = header
        if header["status"] is None:
            findings.append(f"{label} is missing a Status line")
        if header["date"] is None:
            findings.append(f"{label} is missing a Date line")
        if index and f"({path.name})" not in index:
            findings.append(f"{path.name} is not listed in docs/adr/README.md")

    for number, header in sorted(headers.items()):
        targets = header["supersedes"]
        if isinstance(targets, list):
            for target in targets:
                if target not in headers:
                    findings.append(f"{number:04d} supersedes missing ADR {target:04d}")
    return findings


def check_errata(root: Path) -> list[str]:
    path = root / "docs" / "blueprint" / "01-decisions.md"
    if not path.exists() or ERRATA_MARKER not in path.read_text(encoding="utf-8"):
        return ["01-decisions.md is missing the errata block"]
    return []


def check_versions(root: Path) -> list[str]:
    path = root / "docs" / "stack" / "versions.md"
    if not path.exists():
        return ["docs/stack/versions.md is missing"]
    versions = parse_versions_table(path.read_text(encoding="utf-8"))
    findings: list[str] = []
    for component, pin_file in (("Python", ".python-version"), ("Node", ".nvmrc")):
        pin_path = root / pin_file
        pinned = pin_path.read_text(encoding="utf-8").strip() if pin_path.exists() else None
        recorded = versions.get(component)
        if pinned is None:
            findings.append(f"{pin_file} is missing")
        elif recorded is None:
            findings.append(f"versions.md has no {component} row")
        elif recorded != pinned:
            findings.append(f"versions.md {component} {recorded} != {pin_file} {pinned}")
    return findings


def run(root: Path) -> list[str]:
    return check_adrs(root) + check_errata(root) + check_versions(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (default: this checkout)",
    )
    args = parser.parse_args(argv)
    findings = run(args.root)
    for finding in findings:
        print(finding)
    if findings:
        return 1
    print("ADR record OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
