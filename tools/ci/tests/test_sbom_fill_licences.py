"""Tests for tools/ci/sbom_fill_licences.py (STACK-04). Stdlib only.

Run from the repo root: python3 -m unittest tools/ci/tests/test_sbom_fill_licences.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "ci" / "sbom_fill_licences.py"


def _site(tmp: Path, name: str, version: str, metadata: str) -> Path:
    site = tmp / "site-packages"
    info = site / f"{name}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n{metadata}\n", encoding="utf-8"
    )
    return site


def _sbom(tmp: Path, components: list[dict[str, object]]) -> Path:
    path = tmp / "python.cdx.json"
    path.write_text(json.dumps({"bomFormat": "CycloneDX", "components": components}), "utf-8")
    return path


def _run(sbom: Path, site: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(sbom), str(site)],
        capture_output=True,
        text=True,
        check=False,
    )


class FillLicences(unittest.TestCase):
    def test_missing_licence_filled_from_license_field(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            site = _site(tmp, "multidict", "6.9.1", "License: Apache License 2.0")
            sbom = _sbom(tmp, [{"name": "multidict", "version": "6.9.1"}])
            result = _run(sbom, site)
            self.assertEqual(result.returncode, 0, result.stderr)
            comp = json.loads(sbom.read_text("utf-8"))["components"][0]
            self.assertEqual(
                comp["licenses"],
                [{"license": {"name": "Apache License 2.0", "acknowledgement": "declared"}}],
            )
            self.assertIn("multidict@6.9.1", result.stdout)

    def test_existing_licence_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            site = _site(tmp, "yarl", "1.0", "License: GPL-3.0")
            existing = [{"license": {"id": "Apache-2.0"}}]
            sbom = _sbom(tmp, [{"name": "yarl", "version": "1.0", "licenses": existing}])
            self.assertEqual(_run(sbom, site).returncode, 0)
            comp = json.loads(sbom.read_text("utf-8"))["components"][0]
            self.assertEqual(comp["licenses"], existing)

    def test_no_license_field_leaves_component_unknown(self) -> None:
        # The checker then denies it as unknown: filling never invents a licence.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            site = _site(tmp, "mystery", "0.1", "Summary: no licence here")
            sbom = _sbom(tmp, [{"name": "mystery", "version": "0.1"}])
            self.assertEqual(_run(sbom, site).returncode, 0)
            comp = json.loads(sbom.read_text("utf-8"))["components"][0]
            self.assertNotIn("licenses", comp)

    def test_long_licence_text_is_not_used(self) -> None:
        # Some packages paste the whole licence text into License:; that is not a name.
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            site = _site(tmp, "wordy", "1.0", "License: " + "x" * 200)
            sbom = _sbom(tmp, [{"name": "wordy", "version": "1.0"}])
            self.assertEqual(_run(sbom, site).returncode, 0)
            self.assertNotIn("licenses", json.loads(sbom.read_text("utf-8"))["components"][0])

    def test_name_match_is_normalised(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            site = _site(tmp, "Foo_Bar", "2.0", "License: MIT")
            sbom = _sbom(tmp, [{"name": "foo-bar", "version": "2.0"}])
            self.assertEqual(_run(sbom, site).returncode, 0)
            comp = json.loads(sbom.read_text("utf-8"))["components"][0]
            self.assertEqual(comp["licenses"][0]["license"]["name"], "MIT")


if __name__ == "__main__":
    unittest.main()
