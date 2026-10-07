#!/usr/bin/env python3
"""Check the security docs keep their required shape (SECURITY-01). Stdlib only.

Checks:
- docs/security/threat-model.md and docs/security/provenance-log.md exist;
- threat-model.md has the six required `## ` threat areas, each with the four `### ` subsections;
- provenance-log.md has the provenance table header and a table row stating AIP was not used.

Prints one line per missing item and exits 1 if there are any.
Usage: python3 tools/ci/check_security_docs.py [--root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIRED_AREAS = (
    "Field PIN and magic link",
    "Portal",
    "Inbound email and webhooks",
    "Legal records",
    "AI",
    "File uploads and sandboxed workers",
)
REQUIRED_SUBSECTIONS = ("Assets", "Threats (STRIDE)", "Controls", "Residual risk")
PROVENANCE_HEADER = ("Date", "Reference area", "Viewed by", "Statement", "Reviewer")

THREAT_MODEL = Path("docs/security/threat-model.md")
PROVENANCE_LOG = Path("docs/security/provenance-log.md")

HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")

Section = tuple[str, list[str]]


def parse_sections(text: str) -> list[Section]:
    """Return [(h2 title, [h3 titles beneath it])] in document order, skipping code fences."""
    sections: list[Section] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(line)
        if not match:
            continue
        level, title = match.group(1), match.group(2)
        if level == "##":
            sections.append((title, []))
        elif sections:
            sections[-1][1].append(title)
    return sections


def check_threat_model_text(text: str) -> list[str]:
    """Return findings like `missing section "AI"` or `AI: missing "Residual risk"`."""
    by_title: dict[str, list[str]] = {}
    for title, subs in parse_sections(text):
        by_title.setdefault(title, []).extend(subs)
    findings: list[str] = []
    for area in REQUIRED_AREAS:
        if area not in by_title:
            findings.append(f'missing section "{area}"')
            continue
        for sub in REQUIRED_SUBSECTIONS:
            if sub not in by_title[area]:
                findings.append(f'{area}: missing "{sub}"')
    return findings


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            rows.append([cell.strip() for cell in line[1:-1].split("|")])
    return rows


def check_provenance_text(text: str) -> list[str]:
    """Return findings for the provenance table header and the standing AIP row."""
    rows = _table_rows(text)
    findings: list[str] = []
    if not any(tuple(row) == PROVENANCE_HEADER for row in rows):
        findings.append("missing table header")
    has_aip_row = any(
        len(row) == len(PROVENANCE_HEADER)
        and row[1].startswith("AIP")
        and "not read" in " ".join(row).lower()
        and "not copied" in " ".join(row).lower()
        for row in rows
    )
    if not has_aip_row:
        findings.append("missing AIP non-use row")
    return findings


def run(root: Path) -> list[str]:
    findings: list[str] = []
    for rel, checker in (
        (THREAT_MODEL, check_threat_model_text),
        (PROVENANCE_LOG, check_provenance_text),
    ):
        path = root / rel
        if not path.is_file():
            findings.append(f"{rel.as_posix()} is missing")
            continue
        findings.extend(f"{rel.name}: {f}" for f in checker(path.read_text(encoding="utf-8")))
    return findings


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
    print("Security docs OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
