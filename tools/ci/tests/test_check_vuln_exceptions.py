"""Tests for tools/ci/check_vuln_exceptions.py (SECURITY-08). Stdlib only.

Run from the repo root: python3 -m unittest tools/ci/tests/test_check_vuln_exceptions.py
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.ci import check_vuln_exceptions as cve

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "ci" / "check_vuln_exceptions.py"
REPO_FILE = ROOT / "config" / "vuln-exceptions.txt"
TODAY = dt.date(2026, 10, 7)

GOOD = """\
# Header comment.

# why: braces DoS, build-time lint tooling only; no fixed release yet.
CVE-2026-0001 exp:2026-12-31
# why: example GHSA entry with a long enough reason.
GHSA-abcd-efgh-ijkl exp:2027-01-15
"""


class ParseTest(unittest.TestCase):
    def test_good_file_parses(self) -> None:
        entries = cve.parse(GOOD)
        self.assertEqual([e.id for e in entries], ["CVE-2026-0001", "GHSA-abcd-efgh-ijkl"])
        self.assertEqual(entries[0].expires, dt.date(2026, 12, 31))
        self.assertIn("braces", entries[0].reason)
        self.assertEqual(cve.validate(entries, today=TODAY), [])

    def test_entry_without_expiry_fails(self) -> None:
        errors = cve.check_text("# why: a reason that is long.\nCVE-2026-0001\n", today=TODAY)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("exp:YYYY-MM-DD", errors[0])

    def test_expired_entry_fails(self) -> None:
        errors = cve.check_text(
            "# why: a reason that is long.\nCVE-2026-0001 exp:2026-10-06\n", today=TODAY
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("expired on 2026-10-06", errors[0])

    def test_expiry_too_far_ahead_fails(self) -> None:
        errors = cve.check_text(
            "# why: a reason that is long.\nCVE-2026-0001 exp:2027-10-07\n", today=TODAY
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("more than 180 days", errors[0])

    def test_entry_without_reason_fails(self) -> None:
        errors = cve.check_text("CVE-2026-0001 exp:2026-12-31\n", today=TODAY)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("# why:", errors[0])

    def test_bad_id_and_bad_date_fail(self) -> None:
        errors = cve.check_text(
            "# why: a reason that is long.\nNOT-AN-ID exp:2026-12-31\n"
            "# why: a reason that is long.\nCVE-2026-0002 exp:2026-13-40\n",
            today=TODAY,
        )
        self.assertEqual(len(errors), 2, errors)
        self.assertIn("NOT-AN-ID", errors[0])
        self.assertIn("2026-13-40", errors[1])

    def test_duplicate_fails(self) -> None:
        text = "# why: a reason that is long.\nCVE-2026-0001 exp:2026-12-31\n" * 2
        errors = cve.check_text(text, today=TODAY)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("duplicate", errors[0])

    def test_empty_file_is_valid(self) -> None:
        self.assertEqual(cve.check_text("# no exceptions\n", today=TODAY), [])


def advisory(severity: str, ghsa: str, *cves: str) -> dict[str, object]:
    return {
        "severity": severity,
        "github_advisory_id": ghsa,
        "cves": list(cves),
        "module_name": "pkg",
        "title": "t",
    }


class PnpmAuditGateTest(unittest.TestCase):
    def test_high_and_critical_fail_unless_excepted(self) -> None:
        report = {
            "advisories": {
                "1": advisory("high", "GHSA-aaaa-bbbb-cccc", "CVE-2026-0001"),
                "2": advisory("critical", "GHSA-dddd-eeee-ffff"),
                "3": advisory("moderate", "GHSA-gggg-hhhh-iiii", "CVE-2026-0009"),
            }
        }
        findings = cve.pnpm_audit_findings(report, {"CVE-2026-0001"})
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("GHSA-dddd-eeee-ffff", findings[0])

    def test_ghsa_id_also_excepts(self) -> None:
        report = {"advisories": {"1": advisory("high", "GHSA-aaaa-bbbb-cccc", "CVE-2026-0001")}}
        self.assertEqual(cve.pnpm_audit_findings(report, {"GHSA-aaaa-bbbb-cccc"}), [])

    def test_empty_report_passes(self) -> None:
        self.assertEqual(cve.pnpm_audit_findings({"advisories": {}}, set()), [])


class RepoFileTest(unittest.TestCase):
    def test_repo_file_is_valid_today(self) -> None:
        errors = cve.check_text(REPO_FILE.read_text(encoding="utf-8"), today=dt.date.today())
        self.assertEqual(errors, [])


class CliTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
        )

    def test_ids_prints_one_id_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.txt"
            path.write_text(GOOD, encoding="utf-8")
            result = self.run_cli("--file", str(path), "--today", "2026-10-07", "--ids")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.split(), ["CVE-2026-0001", "GHSA-abcd-efgh-ijkl"])

    def test_pnpm_audit_cli_uses_the_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.txt"
            path.write_text(GOOD, encoding="utf-8")
            report = Path(tmp) / "audit.json"
            report.write_text(
                json.dumps(
                    {"advisories": {"1": advisory("high", "GHSA-zzzz-zzzz-zzzz", "CVE-2026-0001")}}
                ),
                encoding="utf-8",
            )
            ok = self.run_cli(
                "--file", str(path), "--today", "2026-10-07", "--pnpm-audit", str(report)
            )
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            path.write_text("# none\n", encoding="utf-8")
            bad = self.run_cli(
                "--file", str(path), "--today", "2026-10-07", "--pnpm-audit", str(report)
            )
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            self.assertIn("CVE-2026-0001", bad.stdout)

    def test_expired_entry_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.txt"
            path.write_text(GOOD, encoding="utf-8")
            result = self.run_cli("--file", str(path), "--today", "2027-01-01")
            self.assertEqual(result.returncode, 1)
            self.assertIn("CVE-2026-0001", result.stdout)


if __name__ == "__main__":
    unittest.main()
