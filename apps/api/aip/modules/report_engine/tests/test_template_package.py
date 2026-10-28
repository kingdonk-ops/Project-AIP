"""REPORTS-01 unit tests: template packages, their contract and hash (no database)."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from aip.modules.report_engine.template_package import (
    CONTRACT_PATH,
    TemplatePackageError,
    load_package,
    parse_package,
)
from aip.platform.db.migrator import repo_root

FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLE = repo_root() / "config" / "report-templates" / "project-summary" / "internal" / "v1"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _copy(tmp_path: Path, source: Path = EXAMPLE) -> Path:
    target = tmp_path / "pkg"
    shutil.copytree(source, target)
    return target


def _error(path: Path) -> TemplatePackageError:
    with pytest.raises(TemplatePackageError) as raised:
        load_package(path)
    return raised.value


def _upload(**changes: Any) -> dict[str, Any]:
    package = load_package(EXAMPLE)
    body: dict[str, Any] = {
        "definition": json.loads(json.dumps(package.definition)),
        "body": package.body,
        "css": package.css,
        "sampleData": dict(package.sample_data),
        "assets": {n: base64.b64encode(a.data).decode() for n, a in package.assets.items()},
    }
    body.update(changes)
    return body


def test_the_baked_contract_matches_the_shared_contract() -> None:
    shared = repo_root() / "packages" / "contracts" / "report-templates"
    assert json.loads(CONTRACT_PATH.read_text("utf-8")) == json.loads(
        (shared / "report-template.schema.json").read_text("utf-8")
    )


def test_the_example_package_loads_and_hashes_stably() -> None:
    first, second = load_package(EXAMPLE), load_package(EXAMPLE)
    assert first.key == "project-summary" and first.variant == "internal" and first.version == 1
    assert first.record_type == "project" and set(first.assets) == {"logo.png"}
    assert len(first.content_sha256) == 64 and first.content_sha256 == second.content_sha256
    assert all(c in "0123456789abcdef" for c in first.content_sha256)


def test_one_byte_of_css_changes_the_hash(tmp_path: Path) -> None:
    copy = _copy(tmp_path)
    style = copy / "style.css"
    style.write_text(style.read_text("utf-8") + " ", encoding="utf-8")
    assert load_package(copy).content_sha256 != load_package(EXAMPLE).content_sha256


def test_an_upload_hashes_like_the_folder() -> None:
    assert parse_package(_upload()).content_sha256 == load_package(EXAMPLE).content_sha256


@pytest.mark.parametrize(
    ("fixture", "code"),
    [
        ("script-tag", "HTML_POLICY"),
        ("external-img", "HTML_POLICY"),
        ("onclick", "HTML_POLICY"),
        ("css-import", "CSS_POLICY"),
        ("include-tag", "HTML_POLICY"),
        ("asset-too-large", "ASSET_TOO_LARGE"),
    ],
)
def test_each_bad_fixture_fails_with_its_code(fixture: str, code: str) -> None:
    error = _error(FIXTURES / fixture)
    assert error.code == code
    if fixture == "include-tag":
        assert [v.rule for v in error.violations] == ["include_not_allowed"]


def test_safe_filter_is_an_html_policy_error(tmp_path: Path) -> None:
    copy = _copy(tmp_path, FIXTURES / "onclick")
    (copy / "body.html.j2").write_text("<p>{{ name|safe }}</p>\n", encoding="utf-8")
    error = _error(copy)
    assert error.code == "HTML_POLICY" and error.path == "body"


def test_a_png_holding_jpeg_bytes_is_a_type_mismatch(tmp_path: Path) -> None:
    copy = _copy(tmp_path)
    (copy / "assets" / "logo.png").write_bytes(JPEG)
    assert _error(copy).code == "ASSET_TYPE_MISMATCH"


def test_an_extra_definition_key_is_schema_invalid_at_its_path(tmp_path: Path) -> None:
    copy = _copy(tmp_path)
    definition = json.loads((copy / "template.json").read_text("utf-8"))
    definition["script"] = "x"
    (copy / "template.json").write_text(json.dumps(definition), encoding="utf-8")
    error = _error(copy)
    assert (error.code, error.path) == ("SCHEMA_INVALID", "script")


def test_template_syntax_errors(tmp_path: Path) -> None:
    copy = _copy(tmp_path, FIXTURES / "onclick")
    (copy / "body.html.j2").write_text("{% if %}", encoding="utf-8")
    assert _error(copy).code == "TEMPLATE_SYNTAX"
    (copy / "body.html.j2").write_text("{{ x | no_such_filter }}", encoding="utf-8")
    assert _error(copy).code == "TEMPLATE_SYNTAX"


def test_assets_must_match_their_declaration(tmp_path: Path) -> None:
    copy = _copy(tmp_path)
    (copy / "assets" / "extra.png").write_bytes(b"\x89PNG")
    error = _error(copy)
    assert (error.code, error.path) == ("SCHEMA_INVALID", "assets.extra.png")


def test_a_font_needs_an_ofl_licence() -> None:
    upload = _upload()
    upload["definition"]["assets"].append({"name": "inter.woff2", "contentType": "font/woff2"})
    upload["assets"]["inter.woff2"] = base64.b64encode(b"wOF2" + b"\x00" * 8).decode()
    with pytest.raises(TemplatePackageError) as raised:
        parse_package(upload)
    assert (raised.value.code, raised.value.path) == ("SCHEMA_INVALID", "fontLicences")
    upload["definition"]["fontLicences"] = ["OFL-1.1"]
    assert "inter.woff2" in parse_package(upload).assets


def test_index_html_is_never_an_asset_name() -> None:
    upload = _upload()
    upload["definition"]["assets"].append({"name": "index.html", "contentType": "image/png"})
    with pytest.raises(TemplatePackageError) as raised:
        parse_package(upload)
    assert raised.value.code == "SCHEMA_INVALID"


def test_bad_base64_and_oversized_bodies() -> None:
    with pytest.raises(TemplatePackageError) as raised:
        parse_package(_upload(assets={"logo.png": "!!not base64!!"}))
    assert (raised.value.code, raised.value.path) == ("SCHEMA_INVALID", "assets.logo.png")
    with pytest.raises(TemplatePackageError) as raised:
        parse_package(_upload(body="x" * (256 * 1024 + 1)))
    assert (raised.value.code, raised.value.path) == ("SCHEMA_INVALID", "body")
