"""SECURITY-08: the daily scan-failure issue body is built from the run's evidence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "scan_failure_report", ROOT / "tools" / "ci" / "scan_failure_report.py"
)
assert _spec and _spec.loader
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)


def test_trivy_findings_lists_each_vulnerability() -> None:
    doc = {
        "Results": [
            {
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-2026-102554",
                        "PkgName": "com.google.guava:guava",
                        "InstalledVersion": "33.6.0-jre",
                        "FixedVersion": "33.7.2",
                        "Severity": "HIGH",
                        "Title": "guava DoS",
                    }
                ]
            }
        ]
    }
    lines = report.trivy_findings(doc)
    assert len(lines) == 1
    assert "CVE-2026-102554" in lines[0] and "33.6.0-jre -> 33.7.2" in lines[0]
    assert report.trivy_findings({}) == []
    assert report.trivy_findings(None) == []


def test_pip_audit_findings_both_shapes() -> None:
    nested = {
        "dependencies": [
            {
                "name": "django",
                "version": "2.2.0",
                "vulns": [{"id": "PYSEC-1", "fix_versions": ["2.2.28"]}],
            }
        ]
    }
    bare = [
        {"name": "django", "version": "2.2.0", "vulns": [{"id": "PYSEC-1", "fix_versions": []}]}
    ]
    assert "PYSEC-1" in report.pip_audit_findings(nested)[0]
    assert "no fix" in report.pip_audit_findings(bare)[0]
    assert report.pip_audit_findings({"dependencies": []}) == []


def test_pnpm_findings_only_high_and_critical() -> None:
    doc = {
        "advisories": {
            "1": {
                "severity": "high",
                "module_name": "braces",
                "title": "ReDoS",
                "github_advisory_id": "GHSA-x",
            },
            "2": {
                "severity": "low",
                "module_name": "noisy",
                "title": "meh",
                "github_advisory_id": "GHSA-y",
            },
        }
    }
    lines = report.pnpm_audit_findings(doc)
    assert len(lines) == 1 and "GHSA-x" in lines[0]


def test_build_body_includes_run_and_findings(tmp_path: Path) -> None:
    (tmp_path / "trivy-aip-keycloak-demo.json").write_text(
        json.dumps(
            {
                "Results": [
                    {
                        "Vulnerabilities": [
                            {"VulnerabilityID": "CVE-2026-102554", "Severity": "HIGH"}
                        ]
                    }
                ]
            }
        )
    )
    body = report.build_body(
        tmp_path, "https://example/run/1", {"images": "failure", "deps": "success"}
    )
    assert "https://example/run/1" in body
    assert "CVE-2026-102554" in body
    assert "aip-keycloak-demo" in body
    assert "images" in body  # the failing job is named


def test_build_body_is_never_empty_without_evidence(tmp_path: Path) -> None:
    body = report.build_body(tmp_path, "https://example/run/2", {"secrets": "failure"})
    assert "https://example/run/2" in body
    assert "No machine-readable findings" in body
