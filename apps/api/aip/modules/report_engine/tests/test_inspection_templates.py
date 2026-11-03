"""REPORTS-03 unit tests: the inspection report packages and the ``autoRender`` contract (no
database).

Both packages render their sample data (the ``inspection-coating`` shape) with the en-AU labels from
``config/terms``; the client variant must hold no responder name, internal tag or id.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from aip.modules.report_engine.render import render_html
from aip.modules.report_engine.template_package import (
    TemplatePackage,
    TemplatePackageError,
    load_package,
)
from aip.platform.db.migrator import repo_root

ROOT = repo_root() / "config" / "report-templates" / "inspection"
INTERNAL, CLIENT = ROOT / "internal" / "v1", ROOT / "client" / "v1"
EXAMPLE = repo_root() / "config" / "report-templates" / "project-summary" / "internal" / "v1"
TERMS: dict[str, str] = json.loads(
    (repo_root() / "config" / "terms" / "en-AU" / "report_engine.json").read_text("utf-8")
)
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _render(package: TemplatePackage, data: dict[str, Any] | None = None) -> str:
    labels = {key: TERMS[key] for key in package.term_keys}
    document = render_html(
        package,
        dict(package.sample_data) if data is None else data,
        labels=labels,
        locale="en-AU",
        time_zone="Australia/Perth",
        unit_system="metric",
    )
    return document.html


@pytest.mark.parametrize("folder", [INTERNAL, CLIENT])
def test_both_packages_load_landscape_and_auto_render_on_approval(folder: Path) -> None:
    package = load_package(folder)
    assert (package.key, package.record_type, package.version) == ("inspection", "inspection", 1)
    assert package.variant == folder.parent.name
    assert package.definition["orientation"] == "landscape"
    assert package.definition["paper"] == "A4"
    assert package.definition["marginsMm"] == {"top": 10, "right": 10, "bottom": 12, "left": 10}
    # ADR 0041: the approved, terminal inspection state is ``performed`` (v1 called it completed).
    assert package.definition["autoRender"] == {"onStates": ["performed"]}


@pytest.mark.parametrize("folder", [INTERNAL, CLIENT])
def test_every_term_key_has_an_en_au_default(folder: Path) -> None:
    package = load_package(folder)
    assert sorted(package.term_keys - TERMS.keys()) == []


def test_the_internal_report_shows_the_tag_responder_and_failed_result() -> None:
    html = _render(load_package(INTERNAL))
    assert "@page { size: A4 landscape;" in html
    assert "P-1001" in html and "AS-000123" in html
    assert "Ivy Inspector" in html
    assert TERMS["report.inspection.result.fail"] in html  # "Fail"
    assert "0.20 mm" in html  # fmt_measure in the project's unit system
    assert "display: table-header-group" in html and "break-inside: avoid" in html


def test_the_client_report_has_no_responder_internal_tag_or_ids() -> None:
    html = _render(load_package(CLIENT))
    assert "@page { size: A4 landscape;" in html
    assert "P-1001" in html and TERMS["report.inspection.result.fail"] in html
    assert "Ivy Inspector" not in html
    assert "AS-000123" not in html
    assert UUID_RE.findall(html) == []
    assert "3f5c0d9e8a7b" not in html  # the form schema hash


def test_a_manual_render_without_approval_says_not_yet_approved() -> None:
    package = load_package(INTERNAL)
    html = _render(package, {**package.sample_data, "approval": {}, "project": None})
    assert TERMS["report.inspection.not_approved"] in html
    assert "Sam Supervisor" not in html


def test_auto_render_needs_a_record_type_with_a_trigger(tmp_path: Path) -> None:
    folder = tmp_path / "pkg"
    shutil.copytree(EXAMPLE, folder)
    definition = json.loads((folder / "template.json").read_text("utf-8"))
    definition["autoRender"] = {"onStates": ["performed"]}
    (folder / "template.json").write_text(json.dumps(definition), "utf-8")
    with pytest.raises(TemplatePackageError) as raised:
        load_package(folder)
    assert (raised.value.code, raised.value.path) == ("SCHEMA_INVALID", "autoRender")


@pytest.mark.parametrize(
    "auto_render",
    [{"onStates": []}, {"onStates": ["Performed"]}, {"onStates": ["performed"], "x": 1}, {}],
)
def test_auto_render_must_match_the_contract(tmp_path: Path, auto_render: Any) -> None:
    folder = tmp_path / "pkg"
    shutil.copytree(INTERNAL, folder)
    definition = json.loads((folder / "template.json").read_text("utf-8"))
    definition["autoRender"] = auto_render
    (folder / "template.json").write_text(json.dumps(definition), "utf-8")
    with pytest.raises(TemplatePackageError) as raised:
        load_package(folder)
    assert raised.value.code == "SCHEMA_INVALID"
    assert raised.value.path.startswith("autoRender")
