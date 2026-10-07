"""Tests for tools/ci/check_security_docs.py (SECURITY-01). Stdlib only.

Run from the repo root: python3 -m unittest tools/ci/test_check_security_docs.py
Integration tests work on temp copies; they never write into the real repo tree.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.ci import check_security_docs as csd

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "ci" / "check_security_docs.py"
THREAT_MODEL = ROOT / "docs" / "security" / "threat-model.md"
PROVENANCE = ROOT / "docs" / "security" / "provenance-log.md"

FULL_SECTION = (
    "### Assets\n\nx\n\n### Threats (STRIDE)\n\nx\n\n### Controls\n\nx\n\n### Residual risk\n\nx\n"
)


class HeadingParserTests(unittest.TestCase):
    def test_committed_threat_model_has_six_areas_in_order(self) -> None:
        sections = csd.parse_sections(THREAT_MODEL.read_text(encoding="utf-8"))
        areas = [title for title, _ in sections if title in csd.REQUIRED_AREAS]
        self.assertEqual(areas, list(csd.REQUIRED_AREAS))

    def test_parser_collects_subheadings_per_area(self) -> None:
        text = "# T\n\n## Portal\n\n" + FULL_SECTION + "\n## AI\n\n### Assets\n"
        sections = csd.parse_sections(text)
        self.assertEqual(sections[0], ("Portal", list(csd.REQUIRED_SUBSECTIONS)))
        self.assertEqual(sections[1], ("AI", ["Assets"]))

    def test_parser_ignores_headings_in_code_fences(self) -> None:
        text = "## Portal\n\n```\n## AI\n### Assets\n```\n"
        self.assertEqual(csd.parse_sections(text), [("Portal", [])])

    def test_ai_without_residual_risk_is_reported(self) -> None:
        text = "## AI\n\n### Assets\n\n### Threats (STRIDE)\n\n### Controls\n"
        findings = csd.check_threat_model_text(text)
        self.assertIn('AI: missing "Residual risk"', findings)

    def test_missing_area_is_reported(self) -> None:
        findings = csd.check_threat_model_text("## Portal\n\n" + FULL_SECTION)
        self.assertIn('missing section "AI"', findings)
        self.assertNotIn('missing section "Portal"', findings)

    def test_complete_text_has_no_findings(self) -> None:
        text = "".join(f"## {area}\n\n{FULL_SECTION}\n" for area in csd.REQUIRED_AREAS)
        self.assertEqual(csd.check_threat_model_text(text), [])


class ProvenanceParserTests(unittest.TestCase):
    def test_committed_log_passes(self) -> None:
        self.assertEqual(csd.check_provenance_text(PROVENANCE.read_text(encoding="utf-8")), [])

    def test_missing_header_is_reported(self) -> None:
        text = "| When | What |\n|---|---|\n"
        self.assertIn("missing table header", csd.check_provenance_text(text))

    def test_header_with_extra_spacing_is_accepted(self) -> None:
        text = (
            "|Date|  Reference area |Viewed by|Statement|Reviewer|\n|---|---|---|---|---|\n"
            "| 2026-10-07 | AIP codebase, schema and data | - | not read, not copied | - |\n"
        )
        self.assertEqual(csd.check_provenance_text(text), [])

    def test_aip_mentioned_outside_table_does_not_count(self) -> None:
        text = (
            "| Date | Reference area | Viewed by | Statement | Reviewer |\n|---|---|---|---|---|\n"
            "\nAIP codebase, schema and data: not read.\n"
        )
        self.assertIn("missing AIP non-use row", csd.check_provenance_text(text))


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        shutil.copytree(ROOT / "docs" / "security", self.root / "docs" / "security")
        self.threat_model = self.root / "docs" / "security" / "threat-model.md"
        self.provenance = self.root / "docs" / "security" / "provenance-log.md"

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

    def test_removed_ai_heading(self) -> None:
        lines = self.threat_model.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [ln for ln in lines if ln.rstrip("\n") != "## AI"]
        self.assertEqual(len(kept), len(lines) - 1)
        self.threat_model.write_text("".join(kept), encoding="utf-8")
        self.assert_fails_with('threat-model.md: missing section "AI"')

    def test_removed_residual_risk_names_area(self) -> None:
        text = self.threat_model.read_text(encoding="utf-8")
        head, sep, tail = text.partition("## Portal\n")
        tail = tail.replace("### Residual risk", "### Leftovers", 1)
        self.threat_model.write_text(head + sep + tail, encoding="utf-8")
        self.assert_fails_with('threat-model.md: Portal: missing "Residual risk"')

    def test_removed_aip_row(self) -> None:
        lines = self.provenance.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [ln for ln in lines if not (ln.startswith("|") and "AIP codebase" in ln)]
        self.assertLess(len(kept), len(lines))
        self.provenance.write_text("".join(kept), encoding="utf-8")
        self.assert_fails_with("provenance-log.md: missing AIP non-use row")

    def test_missing_files(self) -> None:
        self.threat_model.unlink()
        self.provenance.unlink()
        result = self.run_check(self.root)
        self.assertEqual(result.returncode, 1)
        out = result.stdout.splitlines()
        self.assertIn("docs/security/threat-model.md is missing", out)
        self.assertIn("docs/security/provenance-log.md is missing", out)

    def test_committed_tree_passes(self) -> None:
        result = self.run_check(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
