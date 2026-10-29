#!/usr/bin/env python3
"""Build the body of the "Daily security scan failing" issue (SECURITY-08). Stdlib only.

The security workflow runs on a daily schedule so a new CVE in an unchanged base image surfaces
within a day. When a scheduled run fails, the report-scan-failure job downloads this run's evidence
artifacts and calls this script to turn them into one Markdown issue body: the failing findings
(Trivy image CVEs, pip-audit and pnpm audit advisories) plus a link to the run. If no machine-
readable finding is present (a job died before it uploaded evidence), the body still names the
failing jobs and links the run, so the issue is never empty.

Usage:
  scan_failure_report.py --evidence DIR --run-url URL [--job name=result ...] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def trivy_findings(report: Any) -> list[str]:
    """One line per HIGH/CRITICAL image vulnerability in a Trivy JSON report."""
    lines: list[str] = []
    if not isinstance(report, dict):
        return lines
    for result in report.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            fixed = vuln.get("FixedVersion") or "no fix"
            lines.append(
                f"- **{vuln.get('VulnerabilityID')}** ({vuln.get('Severity')}) "
                f"{vuln.get('PkgName')} {vuln.get('InstalledVersion')} -> {fixed}"
                f"{': ' + vuln['Title'] if vuln.get('Title') else ''}"
            )
    return lines


def pip_audit_findings(report: Any) -> list[str]:
    """One line per pip-audit vulnerability (dict-with-dependencies or bare-list formats)."""
    deps = report.get("dependencies") if isinstance(report, dict) else report
    lines: list[str] = []
    for dep in deps or []:
        if not isinstance(dep, dict):
            continue
        for vuln in dep.get("vulns") or []:
            fixed = ", ".join(vuln.get("fix_versions") or []) or "no fix"
            lines.append(
                f"- **{vuln.get('id')}** {dep.get('name')} {dep.get('version')} -> {fixed}"
            )
    return lines


def pnpm_audit_findings(report: Any) -> list[str]:
    """One line per HIGH/CRITICAL pnpm advisory."""
    lines: list[str] = []
    advisories = report.get("advisories") if isinstance(report, dict) else None
    for advisory in (advisories or {}).values():
        if str(advisory.get("severity", "")).lower() not in ("high", "critical"):
            continue
        ident = advisory.get("github_advisory_id") or ", ".join(advisory.get("cves") or [])
        lines.append(
            f"- **{ident}** ({advisory.get('severity')}) {advisory.get('module_name')}: "
            f"{advisory.get('title')}"
        )
    return lines


def _section(title: str, lines: Sequence[str]) -> list[str]:
    return [f"### {title}", "", *lines, ""] if lines else []


def build_body(evidence: Path, run_url: str, jobs: dict[str, str]) -> str:
    """Assemble the Markdown issue body from whatever evidence is present under ``evidence``."""
    out: list[str] = [
        "The scheduled security scan failed. This issue is opened/updated automatically by the "
        "`security` workflow and stays open until the scan passes again.",
        "",
        f"- **Run:** {run_url}",
    ]
    if jobs:
        failed = (
            ", ".join(sorted(n for n, r in jobs.items() if r == "failure")) or "(none reported)"
        )
        out.append(f"- **Failing jobs:** {failed}")
    out.append("")

    trivy: list[str] = []
    for path in sorted(evidence.rglob("trivy-*.json")):
        found = trivy_findings(_load(path))
        if found:
            image = path.stem.removeprefix("trivy-")
            trivy += [f"**{image}**", "", *found, ""]
    out += _section("Image vulnerabilities (Trivy)", trivy)

    for name, func in (
        ("pip-audit.json", pip_audit_findings),
        ("pnpm-audit.json", pnpm_audit_findings),
    ):
        matches = list(evidence.rglob(name))
        lines: list[str] = []
        for path in sorted(matches):
            lines += func(_load(path))
        out += _section(f"Dependencies ({name})", lines)

    if (
        not trivy
        and not any(evidence.rglob("pip-audit.json"))
        and not any(evidence.rglob("pnpm-audit.json"))
    ):
        out += [
            "No machine-readable findings were attached to this run (a job may have failed before "
            "uploading evidence). Open the run above for the logs.",
            "",
        ]
    return "\n".join(out).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the daily scan failure issue body")
    parser.add_argument(
        "--evidence", type=Path, required=True, help="directory of downloaded evidence"
    )
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--out", type=Path, help="write the body here (also printed to stdout)")
    parser.add_argument(
        "--job",
        action="append",
        default=[],
        metavar="NAME=RESULT",
        help="a job name and its result",
    )
    args = parser.parse_args(argv)
    jobs = dict(item.split("=", 1) for item in args.job if "=" in item)
    body = build_body(args.evidence, args.run_url, jobs)
    if args.out is not None:
        args.out.write_text(body, encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
