"""Tests for tools/ci/check_adrs.py (STACK-01). Stdlib only.

Run from the repo root: python3 -m unittest tools/ci/test_check_adrs.py
Integration tests work on temp copies; they never write into the real repo tree.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.ci import check_adrs

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "ci" / "check_adrs.py"


class ParserTests(unittest.TestCase):
    def test_header_parser_on_adr_0002(self) -> None:
        path = ROOT / "docs" / "adr" / "0002-data-access-and-migrations.md"
        header = check_adrs.parse_adr_header(path.name, path.read_text(encoding="utf-8"))
        self.assertEqual(header["number"], 2)
        status = header["status"]
        assert isinstance(status, str)
        self.assertTrue(status.startswith("accepted (matches owner decision "), status)
        self.assertEqual(header["date"], "2026-10-07")
        self.assertIsNone(header["supersedes"])

    def test_header_parser_reads_supersedes(self) -> None:
        text = (
            "# ADR 0011: x\n\n"
            "- **Status:** accepted\n- **Date:** 2026-10-08\n- **Supersedes:** 0003\n"
        )
        header = check_adrs.parse_adr_header("0011-x.md", text)
        self.assertEqual(header["supersedes"], [3])

    def test_header_parser_missing_bullets(self) -> None:
        header = check_adrs.parse_adr_header("0011-x.md", "# ADR 0011: x\n")
        self.assertIsNone(header["status"])
        self.assertIsNone(header["date"])

    def test_versions_table_parser(self) -> None:
        row = "| Python | 3.12 | .python-version | minor bumps by ADR |"
        self.assertEqual(check_adrs.parse_versions_table(row), {"Python": "3.12"})

    def test_versions_table_parser_skips_header_and_rule(self) -> None:
        text = (
            "| Component | Version | Pinned in | Upgrade policy |\n"
            "|---|---|---|---|\n"
            "| Node | 22 | `.nvmrc` | LTS only |\n"
        )
        self.assertEqual(check_adrs.parse_versions_table(text), {"Node": "22"})


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        shutil.copytree(ROOT / "docs", self.root / "docs")
        for name in (".python-version", ".nvmrc"):
            shutil.copy2(ROOT / name, self.root / name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_check(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_fails_with(self, message: str) -> None:
        result = self.run_check(self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stdout.splitlines())

    def test_temp_copy_passes(self) -> None:
        result = self.run_check(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_duplicate_number(self) -> None:
        adr = self.root / "docs" / "adr"
        shutil.copy2(adr / "0002-data-access-and-migrations.md", adr / "0002-duplicate.md")
        self.assert_fails_with("duplicate ADR number 0002")

    def test_supersedes_missing_adr(self) -> None:
        path = self.root / "docs" / "adr" / "0003-jobs-outbox-and-sidecar.md"
        text = path.read_text(encoding="utf-8")
        marker = "- **Date:**"
        text = text.replace(marker, "- **Supersedes:** 0042\n" + marker, 1)
        path.write_text(text, encoding="utf-8")
        self.assert_fails_with("0003 supersedes missing ADR 0042")

    def test_missing_errata_marker(self) -> None:
        path = self.root / "docs" / "blueprint" / "01-decisions.md"
        text = path.read_text(encoding="utf-8").replace(check_adrs.ERRATA_MARKER, "")
        path.write_text(text, encoding="utf-8")
        self.assert_fails_with("01-decisions.md is missing the errata block")

    def test_nvmrc_mismatch(self) -> None:
        (self.root / ".nvmrc").write_text("20\n", encoding="utf-8")
        self.assert_fails_with("versions.md Node 22 != .nvmrc 20")

    def test_python_version_mismatch(self) -> None:
        (self.root / ".python-version").write_text("3.13\n", encoding="utf-8")
        self.assert_fails_with("versions.md Python 3.12 != .python-version 3.13")

    def test_missing_status_and_date(self) -> None:
        path = self.root / "docs" / "adr" / "0007-mvp-scope-and-strangler.md"
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [ln for ln in lines if not ln.startswith(("- **Status:**", "- **Date:**"))]
        path.write_text("".join(kept), encoding="utf-8")
        result = self.run_check(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("0007 is missing a Status line", result.stdout.splitlines())
        self.assertIn("0007 is missing a Date line", result.stdout.splitlines())

    def test_adr_not_in_index(self) -> None:
        adr = self.root / "docs" / "adr"
        text = "# ADR 0099: x\n\n- **Status:** proposed\n- **Date:** 2026-10-07\n"
        (adr / "0099-unlisted.md").write_text(text, encoding="utf-8")
        self.assert_fails_with("0099-unlisted.md is not listed in docs/adr/README.md")

    def test_committed_tree_passes(self) -> None:
        result = self.run_check(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
