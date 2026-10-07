"""Tests for tools/ci/check_licences.py (STACK-04). Stdlib only.

Run from the repo root: python3 -m unittest tools/ci/tests/test_check_licences.py
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tools.ci import check_licences as cl

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "ci" / "check_licences.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
POLICY = ROOT / "config" / "licence-policy.json"
TODAY = dt.date(2099, 1, 1)


def component(name: str, licence: str | None, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"type": "library", "name": name, "version": "1.0.0"}
    entry["purl"] = extra.pop("purl", f"pkg:pypi/{name}@1.0.0")
    if licence is not None:
        key = "expression" if " " in licence else "license"
        entry["licenses"] = [{key: licence} if key == "expression" else {key: {"id": licence}}]
    entry.update(extra)
    return entry


def sbom(*components: dict[str, Any]) -> dict[str, Any]:
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": list(components)}


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


class ClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = cl.load_policy(POLICY)

    def test_spec_examples(self) -> None:
        self.assertEqual(cl.classify("AGPL-3.0-only", self.policy), "deny")
        self.assertEqual(cl.classify("MIT", self.policy), "allow")
        self.assertEqual(cl.classify("LGPL-3.0-or-later", self.policy), "review")
        self.assertEqual(cl.classify("MIT OR GPL-3.0-only", self.policy), "allow")

    def test_and_needs_every_branch(self) -> None:
        self.assertEqual(cl.classify("MIT AND PSF-2.0", self.policy), "allow")
        self.assertEqual(cl.classify("MIT AND GPL-2.0-only", self.policy), "deny")
        self.assertEqual(cl.classify("MIT AND LGPL-2.1-only", self.policy), "review")

    def test_parentheses_and_with(self) -> None:
        self.assertEqual(cl.classify("(MIT OR AGPL-3.0-only) AND Apache-2.0", self.policy), "allow")
        self.assertEqual(cl.classify("(GPL-2.0-only OR SSPL-1.0) AND MIT", self.policy), "deny")
        self.assertEqual(
            cl.classify("GPL-2.0-only WITH Classpath-exception-2.0", self.policy), "deny"
        )

    def test_gpl_agpl_sspl_and_unknown_are_denied(self) -> None:
        for licence in [
            "GPL-2.0-only",
            "GPL-3.0-or-later",
            "AGPL-3.0-or-later",
            "SSPL-1.0",
            "BUSL-1.1",
            "LicenseRef-proprietary",
            "",
        ]:
            with self.subTest(licence=licence):
                self.assertEqual(cl.classify(licence, self.policy), "deny")

    def test_aliases_map_classifier_names(self) -> None:
        name = "License :: OSI Approved :: Apache Software License"
        self.assertEqual(cl.classify(name, self.policy), "allow")
        gpl = "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"
        self.assertEqual(cl.classify(gpl, self.policy), "deny")

    def test_component_licence_entries_are_combined_with_and(self) -> None:
        entry = {
            "licenses": [
                {"license": {"id": "MIT"}},
                {"license": {"name": "License :: OSI Approved :: Apache Software License"}},
            ]
        }
        self.assertEqual(cl.component_licence(entry, self.policy), "MIT AND Apache-2.0")
        self.assertEqual(cl.classify_component(entry, self.policy), "allow")
        entry["licenses"].append({"license": {"id": "GPL-2.0-only"}})
        self.assertEqual(cl.classify_component(entry, self.policy), "deny")
        self.assertEqual(cl.component_licence({}, self.policy), "")
        self.assertEqual(cl.classify_component({}, self.policy), "deny")
        dup = {"licenses": [{"license": {"id": "MIT"}}, {"license": {"name": "MIT"}}]}
        self.assertEqual(cl.component_licence(dup, self.policy), "MIT")


class PolicyTests(unittest.TestCase):
    def test_committed_policy_rejects_copyleft_and_unknown(self) -> None:
        policy = cl.load_policy(POLICY)
        for pattern in ["GPL-*", "AGPL-*", "SSPL-*"]:
            self.assertIn(pattern, policy["deny"])
        for licence in [
            "MIT",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "Apache-2.0",
            "ISC",
            "PSF-2.0",
            "MPL-2.0",
        ]:
            self.assertIn(licence, policy["allow"])
        self.assertIn("LGPL-*", policy["review"])
        self.assertTrue(policy["system_packages"]["deny_names"], "Ghostscript must be named")

    def test_exception_without_required_fields_is_rejected(self) -> None:
        raw = json.loads(POLICY.read_text(encoding="utf-8"))
        raw["exceptions"] = [{"component": "x", "licence": "GPL-2.0-only", "expires": "2099-01-01"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(cl.PolicyError):
                cl.load_policy(path)

    def test_exception_with_bad_date_is_rejected(self) -> None:
        raw = json.loads(POLICY.read_text(encoding="utf-8"))
        raw["exceptions"] = [
            {
                "component": "x",
                "licence": "GPL-2.0-only",
                "reason": "r",
                "approver": "a",
                "expires": "soon",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(cl.PolicyError):
                cl.load_policy(path)


class ExceptionTests(unittest.TestCase):
    def policy_with(self, expires: dt.date) -> cl.Policy:
        policy = cl.load_policy(FIXTURES / "policy_with_exception.json")
        policy["exceptions"][0]["expires"] = expires.isoformat()
        return policy

    def check(self, policy: cl.Policy) -> cl.Report:
        doc = sbom(component("fixture-agpl", "AGPL-3.0-only"))
        return cl.check_documents([("python.cdx.json", doc)], policy, TODAY)

    def test_exception_expiring_yesterday_is_ignored(self) -> None:
        report = self.check(self.policy_with(TODAY - dt.timedelta(days=1)))
        self.assertEqual(len(report.violations), 1)
        self.assertIn("expired", report.violations[0].note)

    def test_exception_expiring_within_30_days_passes_with_warning(self) -> None:
        report = self.check(self.policy_with(TODAY + dt.timedelta(days=30)))
        self.assertEqual(report.violations, [])
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("fixture-agpl", report.warnings[0])

    def test_exception_expiring_later_passes_silently(self) -> None:
        report = self.check(self.policy_with(TODAY + dt.timedelta(days=31)))
        self.assertEqual(report.violations, [])
        self.assertEqual(report.warnings, [])

    def test_exception_expiring_today_still_applies(self) -> None:
        report = self.check(self.policy_with(TODAY))
        self.assertEqual(report.violations, [])

    def test_exception_for_another_licence_does_not_apply(self) -> None:
        policy = self.policy_with(TODAY + dt.timedelta(days=90))
        policy["exceptions"][0]["licence"] = "GPL-3.0-only"
        self.assertEqual(len(self.check(policy).violations), 1)

    def test_exception_can_pin_a_version(self) -> None:
        policy = self.policy_with(TODAY + dt.timedelta(days=90))
        policy["exceptions"][0]["component"] = "fixture-agpl@2.0.0"
        self.assertEqual(len(self.check(policy).violations), 1)
        policy["exceptions"][0]["component"] = "fixture-agpl@1.0.0"
        self.assertEqual(self.check(policy).violations, [])


class DocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = cl.load_policy(POLICY)

    def violations(self, name: str, *components: dict[str, Any]) -> list[cl.Violation]:
        return cl.check_documents([(name, sbom(*components))], self.policy, TODAY).violations

    def test_lgpl_passes_only_in_sandbox_image_sboms(self) -> None:
        lib = component("ifcopenshell", "LGPL-3.0-or-later")
        self.assertEqual(self.violations("image-sandbox-ifc.cdx.json", lib), [])
        found = self.violations("python.cdx.json", lib)
        self.assertEqual([v.component for v in found], ["ifcopenshell@1.0.0"])
        self.assertEqual(self.violations("dist/sbom/image-sandbox-ocr.cdx.json", lib), [])

    def test_component_without_licence_is_denied(self) -> None:
        found = self.violations("js.cdx.json", component("mystery", None))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].licence, "")

    def test_first_party_components_are_skipped(self) -> None:
        self.assertEqual(self.violations("image-api.cdx.json", component("aip", None)), [])
        web = component("web", None, group="@aip", purl="pkg:npm/%40aip/web@0.0.0")
        self.assertEqual(self.violations("js.cdx.json", web), [])

    def test_nested_components_are_checked(self) -> None:
        parent = component("parent", "MIT")
        parent["components"] = [component("child", "AGPL-3.0-only")]
        found = self.violations("python.cdx.json", parent)
        self.assertEqual([v.component for v in found], ["child@1.0.0"])

    def test_system_packages_deny_only_agpl_sspl_and_named_packages(self) -> None:
        bash = component("bash", None, purl="pkg:deb/debian/bash@5.2")
        bash["licenses"] = [
            {"license": {"id": "GPL-3.0-only"}},
            {"license": {"name": "permissive"}},
        ]
        self.assertEqual(self.violations("image-api.cdx.json", bash), [])
        gs = component("ghostscript", "GPL-3.0-only", purl="pkg:deb/debian/ghostscript@10.0")
        libgs = component("libgs10", None, purl="pkg:deb/debian/libgs10@10.0")
        agpl = component("some-daemon", "AGPL-3.0-only", purl="pkg:apk/alpine/some-daemon@1")
        found = self.violations("image-sandbox-ocr.cdx.json", gs, libgs, agpl)
        self.assertEqual(
            [v.component for v in found],
            ["ghostscript@1.0.0", "libgs10@1.0.0", "some-daemon@1.0.0"],
        )

    def test_binaries_without_purl_use_the_system_rule(self) -> None:
        python = {"type": "application", "name": "python", "version": "3.12"}
        self.assertEqual(self.violations("image-api.cdx.json", python), [])
        gs = {"type": "application", "name": "gs", "version": "10"}
        self.assertEqual(len(self.violations("image-api.cdx.json", gs)), 1)

    def test_system_rule_denies_non_spdx_agpl_and_sspl_spellings(self) -> None:
        spellings = [
            "AGPLv3",
            "agplv3+",
            "GNU Affero General Public License v3",
            "(AGPL-3.0",
            "MIT OR AGPL-3.0-only",
            "SSPL",
            "Server Side Public License, v 1",
        ]
        for spelling in spellings:
            with self.subTest(licence=spelling):
                pkg = component("daemon", None, purl="pkg:deb/debian/daemon@1")
                pkg["licenses"] = [{"license": {"name": spelling}}]
                self.assertEqual(len(self.violations("image-api.cdx.json", pkg)), 1)
                pkg["licenses"] = [{"expression": spelling}]
                self.assertEqual(len(self.violations("image-api.cdx.json", pkg)), 1)

    def test_committed_system_deny_has_loose_agpl_sspl_patterns(self) -> None:
        deny = self.policy["system_packages"]["deny"]
        for pattern in ["*AGPL*", "*Affero*", "*SSPL*", "*Server Side Public*"]:
            self.assertIn(pattern, deny)

    def test_system_rule_applies_only_in_image_sboms(self) -> None:
        crate = component("gpl-crate", "GPL-3.0-only", purl="pkg:cargo/gpl-crate@1.0.0")
        gomod = component("gpl-mod", "GPL-2.0-only", purl="pkg:golang/example.com/gpl-mod@1")
        generic = component("gpl-bin", "GPL-3.0-only", purl="pkg:generic/gpl-bin@1")
        binary = {
            "type": "application",
            "name": "gpl-tool",
            "version": "1",
            "licenses": [{"license": {"id": "GPL-3.0-only"}}],
        }
        for name in ["python.cdx.json", "js.cdx.json"]:
            with self.subTest(sbom=name):
                found = self.violations(name, crate, gomod, generic, binary)
                self.assertEqual(len(found), 4)
        self.assertEqual(self.violations("image-api.cdx.json", crate, gomod, generic, binary), [])

    def test_file_and_os_components_are_ignored(self) -> None:
        file_ = {"type": "file", "name": "/usr/lib/x.so"}
        os_ = {"type": "operating-system", "name": "debian", "version": "13"}
        self.assertEqual(self.violations("image-api.cdx.json", file_, os_), [])


class CliTests(unittest.TestCase):
    def test_agpl_fixture_fails_and_names_the_component(self) -> None:
        result = run_cli(str(FIXTURES / "sbom_agpl.json"))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fixture-agpl@1.0.0 AGPL-3.0-only", result.stdout)
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        self.assertEqual(
            events,
            [
                {
                    "event": "security.sbom.policy_violation",
                    "component": "fixture-agpl@1.0.0",
                    "licence": "AGPL-3.0-only",
                    "sbom": "sbom_agpl.json",
                }
            ],
        )
        self.assertTrue(any(line.startswith("::error") for line in result.stdout.splitlines()))

    def test_exception_expiring_in_30_days_passes_with_warning(self) -> None:
        result = run_cli(
            "--policy",
            str(FIXTURES / "policy_with_exception.json"),
            "--today",
            "2099-01-01",
            str(FIXTURES / "sbom_agpl.json"),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("::warning", result.stdout)
        self.assertIn("fixture-agpl", result.stdout)
        self.assertIn("2099-01-31", result.stdout)

    def test_expired_exception_fails(self) -> None:
        result = run_cli(
            "--policy",
            str(FIXTURES / "policy_with_exception.json"),
            "--today",
            "2099-02-01",
            str(FIXTURES / "sbom_agpl.json"),
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fixture-agpl@1.0.0", result.stdout)

    def test_clean_sbom_passes_with_no_output(self) -> None:
        result = run_cli(str(FIXTURES / "sbom_clean.json"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_unreadable_sbom_is_a_usage_error(self) -> None:
        result = run_cli(str(FIXTURES / "does-not-exist.json"))
        self.assertEqual(result.returncode, 2)

    def test_no_sbom_arguments_is_a_usage_error(self) -> None:
        self.assertEqual(run_cli().returncode, 2)


class SbomScriptTests(unittest.TestCase):
    def test_sbom_script_is_valid_bash(self) -> None:
        script = ROOT / "tools" / "sbom.sh"
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
