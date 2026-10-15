"""TERMS-07: the hard-coded label scanner (unit tests, and the tests/fixtures/lint integration)."""

from __future__ import annotations

import json
from pathlib import Path

from aip.modules.terms.lint import Finding, main, scan

REPO_ROOT = Path(__file__).resolve().parents[6]
DICTIONARY = REPO_ROOT / "config" / "terms" / "en-AU"
FIXTURES = Path(__file__).parent / "fixtures" / "lint"
NCR_TEMPLATE = "templates/email/ncr_raised.j2"


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _scan(root: Path, allowlist: Path | None = None) -> list[Finding]:
    return scan(sources=root, dictionary=DICTIONARY, base=root, allowlist=allowlist)


# --- templates ----------------------------------------------------------------------------------


def test_template_text_flags_ncr_with_its_key(tmp_path: Path) -> None:
    _write(tmp_path, "templates/x.j2", "Raise NCR now\n")
    assert _scan(tmp_path) == [Finding("templates/x.j2", 1, 7, "NCR", "record.type.ncr")]


def test_template_expressions_comments_and_statements_are_not_flagged(tmp_path: Path) -> None:
    _write(tmp_path, "templates/x.j2", '{{ "NCR" }}\n{% if k == "NCR" %}{% endif %}\n{# NCR #}\n')
    assert _scan(tmp_path) == []


def test_abbreviations_are_case_sensitive_and_words_are_not(tmp_path: Path) -> None:
    _write(tmp_path, "templates/x.j2", "an ncr list\nA VARIATION here\n")
    assert _scan(tmp_path) == [
        Finding("templates/x.j2", 2, 3, "Variation", "record.type.variation")
    ]


def test_matches_are_whole_words(tmp_path: Path) -> None:
    _write(tmp_path, "templates/x.j2", "NCRs and Variations and ITPS\n")
    assert _scan(tmp_path) == []


def test_j2_outside_a_templates_folder_and_tests_folders_are_not_scanned(tmp_path: Path) -> None:
    _write(tmp_path, "other/x.j2", "Raise NCR\n")
    _write(tmp_path, "mod/tests/templates/x.j2", "Raise NCR\n")
    _write(tmp_path, "mod/tests/schemas.py", 'class A:\n    label: str = "NCR"\n')
    assert _scan(tmp_path) == []


def test_line_numbers_count_newlines_only(tmp_path: Path) -> None:
    _write(tmp_path, "templates/x.j2", "a\fb\nRaise NCR\n")
    assert [f.line for f in _scan(tmp_path)] == [2]


# --- schemas.py ---------------------------------------------------------------------------------


def test_schema_label_fields_defaults_field_calls_and_literals_are_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mod/schemas.py",
        "from typing import Literal\n"
        "from pydantic import BaseModel, Field\n"
        "class A(BaseModel):\n"
        '    label: str = "NCR"\n'
        '    title: str = Field("Variation", max_length=10)\n'
        '    display_name: str = Field(default="ITP")\n'
        '    kind: Literal["NCR"] = "NCR"\n'
        '    label2: str = "NCR"\n'
        'class B(BaseModel):\n    title: Literal["MEWP", "x"]\n',
    )
    found = [(f.line, f.term) for f in _scan(tmp_path)]
    assert found == [(4, "NCR"), (5, "Variation"), (6, "ITP"), (10, "MEWP")]


# --- allow-list ---------------------------------------------------------------------------------


def test_an_allow_listed_occurrence_is_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "templates/x.j2", "Raise NCR\nRaise NCR again\n")
    allow = _write(
        tmp_path,
        "allow.toml",
        '[[allow]]\npath = "templates/*.j2"\nline_pattern = "again$"\nterm = "NCR"\n'
        'reason = "fixture: quoted from the client contract"\n',
    )
    assert [f.line for f in _scan(tmp_path, allow)] == [1]


def test_an_allow_list_entry_without_a_reason_is_a_finding_and_allows_nothing(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "templates/x.j2", "Raise NCR\n")
    allow = _write(
        tmp_path,
        "allow.toml",
        '# comment [[allow]]\n\n[[allow]]\npath = "templates/*.j2"\nline_pattern = "NCR"\n'
        'term = "NCR"\n',
    )
    assert _scan(tmp_path, allow) == [
        Finding("allow.toml", 3, 1, "NCR", None),
        Finding("templates/x.j2", 1, 7, "NCR", "record.type.ncr"),
    ]


# --- integration over tests/fixtures/lint -------------------------------------------------------


def test_fixture_scan_finds_exactly_the_template_and_schema_lines() -> None:
    found = [(f.file, f.line, f.term, f.suggested_key) for f in _scan(FIXTURES)]
    assert found == [
        ("schemas.py", 7, "Variation", "record.type.variation"),
        (NCR_TEMPLATE, 3, "NCR", "record.type.ncr"),
    ]


def test_cli_writes_findings_json_and_exits_1(tmp_path: Path) -> None:
    out = tmp_path / "out" / "findings.json"
    args = ["--root", str(REPO_ROOT), "--sources", str(FIXTURES), "--out", str(out)]
    assert main(args) == 1
    body = json.loads(out.read_text(encoding="utf-8"))
    assert [(f["line"], f["term"]) for f in body] == [(7, "Variation"), (3, "NCR")]
    assert set(body[0]) == {"file", "line", "column", "term", "suggested_key"}
    assert body[1]["file"].endswith("tests/fixtures/lint/" + NCR_TEMPLATE)
    assert main([*args, "--report-only"]) == 0


def test_cli_exits_0_when_clean(tmp_path: Path) -> None:
    out = tmp_path / "findings.json"
    assert main(["--root", str(REPO_ROOT), "--sources", str(tmp_path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == []


def test_the_api_source_tree_is_clean() -> None:
    """What the CI ``terms-lint`` job enforces, so a raw label fails locally too."""
    assert main(["--root", str(REPO_ROOT)]) == 0
