"""DESIGN-03: the Python CSV writer reproduces the shared golden vectors byte for byte."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aip.platform.http.csv import csv_cell, csv_header, csv_row, to_csv

VECTORS = Path(__file__).resolve().parents[5] / "packages/contracts/csv-vectors/csv-v1.json"
CASES: list[dict[str, Any]] = json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden_vectors(case: dict[str, Any]) -> None:
    assert to_csv(case["columns"], case["rows"]) == case["expected"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_streamed_header_and_rows_match_the_vectors(case: dict[str, Any]) -> None:
    """PROJECTS-06: a streamed export (header, then row by row) writes the same bytes."""
    rows = "".join(csv_row(case["columns"], row) for row in case["rows"])
    assert csv_header(case["columns"]) + rows == case["expected"]


def test_formula_payload_is_neutralised() -> None:
    assert csv_cell('=HYPERLINK("x")') == '"\'=HYPERLINK(""x"")"'
