#!/usr/bin/env python3
"""Validate the vulnerability exception file (SECURITY-08). Stdlib only.

config/vuln-exceptions.txt lists the vulnerabilities the security scans accept for now. It is in
Trivy's ignore-file format, so Trivy reads it as is (``--ignorefile``) and itself stops ignoring an
entry once its ``exp:`` date passes. pip-audit gets the IDs from ``--ids`` (``--ignore-vuln``).
pnpm audit's own ``--ignore`` writes the ID into pnpm-workspace.yaml with no expiry, so its JSON
report is gated here instead: ``--pnpm-audit REPORT.json`` fails on any HIGH/CRITICAL advisory
that no entry covers (by CVE or GHSA id).

Rules, one finding per broken entry:
- each entry is ``<ID> exp:YYYY-MM-DD``; the ID is a CVE, GHSA or PYSEC id;
- the line right above it is ``# why: <reason>`` (who accepted it and why);
- the expiry is in the future and at most 180 days ahead, so every exception is re-reviewed;
- no ID appears twice.

Usage: python3 tools/ci/check_vuln_exceptions.py [--file PATH] [--today YYYY-MM-DD]
       [--ids | --pnpm-audit REPORT.json]
Exits 1 on findings; with --ids prints the IDs (one per line) when the file is valid.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GATED_SEVERITIES = ("high", "critical")

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "config" / "vuln-exceptions.txt"
MAX_DAYS = 180
VULN_ID = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA(-[a-z0-9]{4}){3}|PYSEC-\d{4}-\d+)$")
WHY = re.compile(r"^#\s*why:\s*(\S.{8,})$")


@dataclass(frozen=True)
class VulnException:
    id: str
    expires: dt.date | None
    reason: str
    line: int
    problem: str = ""


def parse(text: str) -> list[VulnException]:
    entries: list[VulnException] = []
    previous = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            previous = ""
            continue
        if line.startswith("#"):
            previous = line
            continue
        why = WHY.match(previous)
        reason = why.group(1).strip() if why else ""
        previous = ""
        fields = line.split()
        vuln_id, rest = fields[0], fields[1:]
        expiry: dt.date | None = None
        problem = ""
        if len(rest) != 1 or not rest[0].startswith("exp:"):
            problem = "expected '<ID> exp:YYYY-MM-DD'"
        else:
            try:
                expiry = dt.date.fromisoformat(rest[0][4:])
            except ValueError:
                problem = f"bad expiry date {rest[0][4:]!r}"
        entries.append(VulnException(vuln_id, expiry, reason, number, problem))
    return entries


def validate(entries: Sequence[VulnException], today: dt.date) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for e in entries:
        where = f"line {e.line}: {e.id}"
        if e.problem:
            errors.append(f"{where}: {e.problem}")
        elif not VULN_ID.match(e.id):
            errors.append(f"{where}: not a CVE, GHSA or PYSEC id")
        elif not e.reason:
            errors.append(f"{where}: needs a '# why: <reason>' comment on the line above")
        elif e.expires is not None and e.expires <= today:
            errors.append(f"{where}: expired on {e.expires.isoformat()} (fix it or re-review)")
        elif e.expires is not None and (e.expires - today).days > MAX_DAYS:
            errors.append(f"{where}: expiry is more than {MAX_DAYS} days ahead")
        elif e.id in seen:
            errors.append(f"{where}: duplicate entry")
        seen.add(e.id)
    return errors


def check_text(text: str, today: dt.date) -> list[str]:
    return validate(parse(text), today)


def pnpm_audit_findings(report: dict[str, Any], accepted: set[str]) -> list[str]:
    """HIGH/CRITICAL advisories in a ``pnpm audit --json`` report that no exception covers."""
    findings: list[str] = []
    advisories: dict[str, Any] = report.get("advisories") or {}
    for advisory in advisories.values():
        severity = str(advisory.get("severity", "")).lower()
        if severity not in GATED_SEVERITIES:
            continue
        ghsa = str(advisory.get("github_advisory_id", ""))
        cves = sorted(str(c) for c in advisory.get("cves") or [])
        if ({ghsa, *cves}) & accepted:
            continue
        findings.append(
            f"pnpm audit: {severity} {ghsa} {cves} in {advisory.get('module_name')}: "
            f"{advisory.get('title')}"
        )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate config/vuln-exceptions.txt")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--ids", action="store_true", help="print the IDs when the file is valid")
    parser.add_argument(
        "--pnpm-audit", type=Path, help="gate a `pnpm audit --json` report on HIGH/CRITICAL"
    )
    args = parser.parse_args(argv)
    text = args.file.read_text(encoding="utf-8")
    errors = check_text(text, args.today)
    for error in errors:
        print(f"{args.file}: {error}")
    if errors:
        return 1
    if args.pnpm_audit is not None:
        report = json.loads(args.pnpm_audit.read_text(encoding="utf-8"))
        findings = pnpm_audit_findings(report, {e.id for e in parse(text)})
        for finding in findings:
            print(finding)
        print(f"pnpm audit: {len(findings)} HIGH/CRITICAL advisory(ies) not excepted")
        return 1 if findings else 0
    if args.ids:
        print("\n".join(e.id for e in parse(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
