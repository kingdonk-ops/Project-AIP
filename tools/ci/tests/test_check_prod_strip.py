"""Tests for tools/ci/check_prod_strip.py (SECURITY-08). Stdlib only.

Run from the repo root: python3 -m unittest tools/ci/tests/test_check_prod_strip.py
The image-level checks (docker build, import inside the image) live in
apps/api/tests/security/test_prod_build_strip.py.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.ci import check_prod_strip as cps

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools" / "ci" / "check_prod_strip.py"
MANIFEST = ROOT / "config" / "prod-strip-manifest.txt"

BLUEPRINT_FIVE = {
    "aip.fixtures.admin",
    "aip.modules.architecture_map",
    "aip.modules.module_builder",
    "aip.modules.pipelines",
    "aip.modules.compliance_dsl",
}


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ManifestParserTest(unittest.TestCase):
    def test_repo_manifest_has_the_five_forbidden_entries(self) -> None:
        manifest = cps.load_manifest(MANIFEST)
        self.assertEqual(len(manifest.forbidden), 5)
        self.assertEqual({e.value for e in manifest.forbidden}, BLUEPRINT_FIVE)

    def test_repo_manifest_lists_the_debug_route_and_dev_code(self) -> None:
        manifest = cps.load_manifest(MANIFEST)
        self.assertIn("/api/v1/_debug", manifest.routes)
        self.assertIn("pytest", manifest.dev_modules)
        self.assertIn("aip.modules._template", manifest.dev_modules)
        self.assertIn("**/*.map", manifest.web_globs)
        self.assertIn("jsxDEV", manifest.web_markers)

    def test_comments_blank_lines_and_trailing_comments_are_ignored(self) -> None:
        manifest = cps.parse_manifest(
            "# header\n\nforbidden  a.b   # why\nroute /x\nweb-marker $Ref$\n"
        )
        self.assertEqual([e.value for e in manifest.forbidden], ["a.b"])
        self.assertEqual(manifest.forbidden[0].reason, "why")
        self.assertEqual(manifest.routes, ("/x",))
        self.assertEqual(manifest.web_markers, ("$Ref$",))

    def test_unknown_kind_is_an_error(self) -> None:
        with self.assertRaisesRegex(cps.ManifestError, "line 1: unknown kind 'forbid'"):
            cps.parse_manifest("forbid a.b\n")

    def test_missing_value_is_an_error(self) -> None:
        with self.assertRaisesRegex(cps.ManifestError, "line 2: expected"):
            cps.parse_manifest("route /x\nforbidden\n")

    def test_bad_module_name_is_an_error(self) -> None:
        with self.assertRaisesRegex(cps.ManifestError, "not a dotted module name"):
            cps.parse_manifest("forbidden aip/modules/x\n")

    def test_empty_manifest_is_an_error(self) -> None:
        with self.assertRaisesRegex(cps.ManifestError, "no forbidden entries"):
            cps.parse_manifest("# nothing\n")


class PackageTreeTest(unittest.TestCase):
    """The installed-package scan: forbidden module paths and test files."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.site = Path(self._tmp.name)
        write(self.site / "aip" / "__init__.py")
        write(self.site / "aip" / "main.py")
        write(self.site / "aip" / "modules" / "ops" / "routes.py")
        self.manifest = cps.load_manifest(MANIFEST)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_clean_tree_passes(self) -> None:
        self.assertEqual(cps.scan_package_tree(self.site, self.manifest), [])

    def test_each_forbidden_package_fails(self) -> None:
        for module in sorted(BLUEPRINT_FIVE):
            with self.subTest(module=module):
                path = self.site.joinpath(*module.split(".")) / "__init__.py"
                write(path)
                errors = cps.scan_package_tree(self.site, self.manifest)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(module, errors[0])
                path.unlink()
                path.parent.rmdir()

    def test_forbidden_single_file_module_fails(self) -> None:
        write(self.site / "aip" / "modules" / "module_builder.py")
        errors = cps.scan_package_tree(self.site, self.manifest)
        self.assertTrue(any("aip.modules.module_builder" in e for e in errors), errors)

    def test_forbidden_bytecode_only_module_fails(self) -> None:
        write(self.site / "aip" / "modules" / "pipelines" / "__pycache__" / "x.cpython-312.pyc")
        errors = cps.scan_package_tree(self.site, self.manifest)
        self.assertTrue(any("aip.modules.pipelines" in e for e in errors), errors)

    def test_test_files_and_template_fail(self) -> None:
        write(self.site / "aip" / "modules" / "ops" / "tests" / "test_health.py")
        write(self.site / "aip" / "conftest.py")
        write(self.site / "aip" / "modules" / "_template" / "routes.py")
        errors = "\n".join(cps.scan_package_tree(self.site, self.manifest))
        self.assertIn("aip/modules/ops/tests", errors)
        self.assertIn("aip/conftest.py", errors)
        self.assertIn("aip.modules._template", errors)


class ImportAndRouteChecksTest(unittest.TestCase):
    def test_importable_module_fails(self) -> None:
        found = {"pytest", "aip.modules.module_builder"}
        errors = cps.check_imports(
            ["pytest", "aip.modules.module_builder", "hypothesis"], lambda m: m in found
        )
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(all("importable" in e for e in errors))

    def test_debug_route_fails(self) -> None:
        errors = cps.check_routes(
            ["/api/v1/health", "/api/v1/_debug/context"], ["/api/v1/_debug"], label="prod"
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("/api/v1/_debug/context", errors[0])

    def test_prefix_match_is_on_path_segments(self) -> None:
        # /api/v1/_debugger is not under /api/v1/_debug.
        self.assertEqual(cps.check_routes(["/api/v1/_debugger"], ["/api/v1/_debug"], "x"), [])
        self.assertEqual(len(cps.check_routes(["/api/v1/_debug"], ["/api/v1/_debug"], "x")), 1)


class ImagePathTest(unittest.TestCase):
    def test_existing_image_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app" / "tools").mkdir(parents=True)
            errors = cps.check_image_paths(["/app/tools", "/app/docs"], root=root)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("/app/tools", errors[0])


class WebDistTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dist = Path(self._tmp.name)
        write(self.dist / "index.html", '<div id="root"></div><script src="/assets/i.js"></script>')
        write(self.dist / "assets" / "i.js", "console.log('prod');")
        self.manifest = cps.load_manifest(MANIFEST)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_prod_dist_passes(self) -> None:
        self.assertEqual(cps.scan_web_dist(self.dist, self.manifest), [])

    def test_source_map_file_fails(self) -> None:
        write(self.dist / "assets" / "i.js.map", "{}")
        errors = cps.scan_web_dist(self.dist, self.manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("assets/i.js.map", errors[0])

    def test_dev_runtime_markers_fail(self) -> None:
        for marker in ("jsxDEV", "sourceMappingURL=", "/@vite/client", "$RefreshReg$"):
            with self.subTest(marker=marker):
                write(self.dist / "assets" / "i.js", f"var a = 1; {marker}")
                errors = cps.scan_web_dist(self.dist, self.manifest)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(marker, errors[0])

    def test_dev_session_stub_chunk_and_marker_fail(self) -> None:
        # DESIGN-02: the fixture-backed session stub must never reach a production build.
        write(self.dist / "assets" / "dev-session-stub-AbC123.js", "export const x = 1;")
        errors = cps.scan_web_dist(self.dist, self.manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("dev-session-stub", errors[0])
        (self.dist / "assets" / "dev-session-stub-AbC123.js").unlink()
        write(self.dist / "assets" / "i.js", "throw new Error('AIP_DEV_SESSION_STUB must not load')")
        errors = cps.scan_web_dist(self.dist, self.manifest)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("AIP_DEV_SESSION_STUB", errors[0])

    def test_empty_dist_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            errors = cps.scan_web_dist(Path(tmp), self.manifest)
            self.assertEqual(len(errors), 1)
            self.assertIn("index.html", errors[0])


class CliTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
        )

    def test_list_prints_the_forbidden_entries(self) -> None:
        result = self.run_cli("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.split()), BLUEPRINT_FIVE)

    def test_web_dist_cli_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write(dist / "index.html", "<div id=root></div>")
            ok = self.run_cli("web-dist", str(dist))
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            write(dist / "assets" / "x.js", "jsxDEV(")
            bad = self.run_cli("web-dist", str(dist))
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            self.assertIn("jsxDEV", bad.stdout)


if __name__ == "__main__":
    unittest.main()
