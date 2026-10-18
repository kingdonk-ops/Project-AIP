"""CSV for register exports (DESIGN-03): the Python twin of ``packages/ui`` ``toCsv``.

RFC 4180 quoting, a UTF-8 BOM and CRLF line ends. A cell a spreadsheet would run as a formula
(starting with ``=``, ``+``, ``-``, ``@``, tab or CR) gets a leading ``'``. Both writers must
reproduce ``packages/contracts/csv-vectors/csv-v1.json`` byte for byte; module export endpoints use
this function so the server and the client agree. A streamed export writes ``csv_header`` once and
then ``csv_row`` per row: the concatenation is exactly ``to_csv``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, Final

__all__ = ["CsvColumn", "csv_cell", "csv_header", "csv_row", "to_csv"]

BOM: Final = "﻿"
_FORMULA_START: Final = re.compile(r"^[=+\-@\t\r]")
_NEEDS_QUOTES: Final = re.compile(r'[",\r\n]')

CsvColumn = Mapping[str, str]  # {"id": ..., "header": ...?}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def csv_cell(value: Any) -> str:
    text = _text(value)
    if _FORMULA_START.match(text):
        text = "'" + text
    if _NEEDS_QUOTES.search(text):
        return '"' + text.replace('"', '""') + '"'
    return text


def csv_header(columns: Sequence[CsvColumn]) -> str:
    """The BOM and the header line, with its line end."""
    return BOM + ",".join(csv_cell(c.get("header", c["id"])) for c in columns) + "\r\n"


def csv_row(columns: Sequence[CsvColumn], row: Mapping[str, Any]) -> str:
    """One data line, with its line end."""
    return ",".join(csv_cell(row.get(c["id"])) for c in columns) + "\r\n"


def to_csv(columns: Sequence[CsvColumn], rows: Iterable[Mapping[str, Any]]) -> str:
    return csv_header(columns) + "".join(csv_row(columns, row) for row in rows)
