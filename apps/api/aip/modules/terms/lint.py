"""Hard-coded label scanner (TERMS-07).

    python -m aip.modules.terms.lint --out terms-lint-findings.json

Builds a deny-list from the default texts in ``config/terms/en-AU/*.json`` and reports each place
one appears as a raw label under ``apps/api/aip`` (``tests`` folders are skipped):

- Jinja templates (``**/templates/**/*.j2``), text nodes only: ``{{ }}``, ``{% %}`` and ``{# #}``
  are blanked before matching;
- ``**/schemas.py``: string literals given to class fields named ``label``, ``title`` or
  ``display_name``, as a default (``= "..."``, ``Field("...")``, ``Field(default="...")``) or as a
  ``Literal[...]`` value in the annotation.

Matching is whole-word. A text in capitals (ITP, NCR, MEWP) matches case-sensitively, any other
text case-insensitively. Texts holding ICU arguments (``{count}``) are skipped, and where two texts
overlap the longer one wins. ``suggested_key`` is the first key (sorted) whose default text matches.
The ESLint rule ``no-hardcoded-labels`` (``packages/config-eslint``) applies the same rules to JSX.

``config/terms/lint-allowlist.toml`` holds ``[[allow]]`` entries ``{path, line_pattern, term,
reason}``: ``path`` is a glob on the repo-relative file and ``line_pattern`` a regex searched in the
source line. An entry without a ``reason`` allows nothing and is reported as a finding itself.

The findings are written as a JSON list of ``{file, line, column, term, suggested_key}`` (lines
and columns 1-based), and the exit code is 1 when the list is non-empty. ``--report-only`` always
exits 0: the API image build uses it to bake the report in for ``GET /api/v1/terms/coverage``.

Standard library only, so CI and the image build can run it as a plain script.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

__all__ = ["Finding", "Term", "build_deny_list", "find_terms", "main", "scan"]

LABEL_FIELDS = frozenset({"label", "title", "display_name"})
SKIPPED_DIRS = frozenset({"tests", "__pycache__", "node_modules"})
# Capitals, digits and joiners only (ITP, NCR, MEWP, QA/QC): matched case-sensitively.
_ABBREVIATION_RE = re.compile(r"[A-Z0-9&/-]*[A-Z][A-Z0-9&/-]*")
_JINJA_RE = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_ALLOW_HEADER = "[[allow]]"


@dataclass(frozen=True, slots=True)
class Term:
    text: str
    key: str
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class Finding:
    file: str
    line: int
    column: int
    term: str
    suggested_key: str | None


@dataclass(frozen=True, slots=True)
class _Allow:
    path: str
    line_pattern: re.Pattern[str]
    term: str


def _default_texts(directory: Path) -> dict[str, str]:
    """``text -> key`` for every usable default text (the first key, sorted, when several share)."""
    pairs: list[tuple[str, str]] = []
    for file in sorted(directory.glob("*.json")):
        raw = cast(object, json.loads(file.read_text(encoding="utf-8")))
        if not isinstance(raw, dict):
            raise ValueError(f"{file}: expected an object of keys")
        for key, value in cast(dict[str, object], raw).items():
            text = value if isinstance(value, str) else None
            if isinstance(value, dict):
                candidate = cast(dict[str, object], value).get("text")
                text = candidate if isinstance(candidate, str) else None
            if text is None:
                continue
            text = " ".join(text.split())
            if text and "{" not in text:
                pairs.append((key, text))
    by_text: dict[str, str] = {}
    for key, text in sorted(pairs):
        by_text.setdefault(text, key)
    return by_text


def build_deny_list(directory: Path) -> list[Term]:
    """The deny-list from a dictionary directory, longest text first."""
    terms: list[Term] = []
    for text, key in _default_texts(directory).items():
        body = r"\s+".join(re.escape(word) for word in text.split(" "))
        flags = 0 if _ABBREVIATION_RE.fullmatch(text) else re.IGNORECASE
        terms.append(Term(text, key, re.compile(rf"(?<!\w){body}(?!\w)", flags)))
    return sorted(terms, key=lambda t: (-len(t.text), t.text))


def find_terms(text: str, terms: Sequence[Term]) -> list[tuple[int, Term]]:
    """``(offset, term)`` for each non-overlapping match in ``text``, in order."""
    claimed: list[tuple[int, int]] = []
    hits: list[tuple[int, Term]] = []
    for term in terms:
        for match in term.pattern.finditer(text):
            start, end = match.span()
            if any(start < e and s < end for s, e in claimed):
                continue
            claimed.append((start, end))
            hits.append((start, term))
    return sorted(hits, key=lambda hit: hit[0])


def _relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _scanned(sources: Path, pattern: str) -> Iterator[Path]:
    for path in sorted(sources.rglob(pattern)):
        if not SKIPPED_DIRS.intersection(path.relative_to(sources).parts):
            yield path


def _template_hits(source: str, terms: Sequence[Term]) -> Iterator[tuple[int, int, Term]]:
    blanked = _JINJA_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), source)
    for number, line in enumerate(blanked.splitlines(), 1):
        for offset, term in find_terms(line, terms):
            yield number, offset + 1, term


def _literal_strings(annotation: ast.expr) -> Iterator[ast.Constant]:
    """String constants inside any ``Literal[...]`` in ``annotation``."""
    for node in ast.walk(annotation):
        if not isinstance(node, ast.Subscript):
            continue
        name = node.value
        if (isinstance(name, ast.Name) and name.id == "Literal") or (
            isinstance(name, ast.Attribute) and name.attr == "Literal"
        ):
            for inner in ast.walk(node.slice):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    yield inner


def _default_strings(value: ast.expr | None) -> Iterator[ast.Constant]:
    """The string default of a field: ``= "x"``, ``Field("x")`` or ``Field(default="x")``."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        yield value
    elif isinstance(value, ast.Call):
        candidates = [*value.args[:1], *(k.value for k in value.keywords if k.arg == "default")]
        for node in candidates:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield node


def _schema_hits(
    source: str, filename: str, terms: Sequence[Term]
) -> Iterator[tuple[int, int, Term]]:
    for cls in ast.walk(ast.parse(source, filename=filename)):
        if not isinstance(cls, ast.ClassDef):
            continue
        for stmt in cls.body:
            if not (
                isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id in LABEL_FIELDS
            ):
                continue
            for node in [*_literal_strings(stmt.annotation), *_default_strings(stmt.value)]:
                for offset, term in find_terms(cast(str, node.value), terms):
                    # col_offset is the opening quote (0-based); the text starts one later.
                    yield node.lineno, node.col_offset + 2 + offset, term


def _load_allowlist(path: Path | None, base: Path) -> tuple[list[_Allow], list[Finding]]:
    if path is None or not path.is_file():
        return [], []
    source = path.read_text(encoding="utf-8")
    headers = [n for n, line in enumerate(source.splitlines(), 1) if line.strip() == _ALLOW_HEADER]
    raw_entries = cast(list[object], tomllib.loads(source).get("allow", []))
    entries: list[_Allow] = []
    problems: list[Finding] = []
    for index, raw in enumerate(raw_entries):
        entry = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
        fields = {name: entry.get(name) for name in ("path", "line_pattern", "term", "reason")}
        term = fields["term"] if isinstance(fields["term"], str) else ""
        line = headers[index] if index < len(headers) else 1
        if not all(isinstance(v, str) and v.strip() for v in fields.values()):
            problems.append(Finding(_relative(path, base), line, 1, term, None))
            continue
        try:
            pattern = re.compile(cast(str, fields["line_pattern"]))
        except re.error:
            problems.append(Finding(_relative(path, base), line, 1, term, None))
            continue
        entries.append(_Allow(cast(str, fields["path"]), pattern, term))
    return entries, problems


def _allowed(entries: Sequence[_Allow], file: str, source_line: str, term: str) -> bool:
    return any(
        e.term == term and fnmatch.fnmatchcase(file, e.path) and e.line_pattern.search(source_line)
        for e in entries
    )


def scan(
    *, sources: Path, dictionary: Path, base: Path, allowlist: Path | None = None
) -> list[Finding]:
    """Every raw label under ``sources``, with files relative to ``base``, sorted."""
    terms = build_deny_list(dictionary)
    entries, findings = _load_allowlist(allowlist, base)
    jobs = [
        *((p, "template") for p in _scanned(sources, "*.j2") if "templates" in p.parts),
        *((p, "schema") for p in _scanned(sources, "schemas.py")),
    ]
    for path, kind in jobs:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        file = _relative(path, base)
        hits = (
            _template_hits(source, terms)
            if kind == "template"
            else _schema_hits(source, str(path), terms)
        )
        for line, column, term in hits:
            if not _allowed(entries, file, lines[line - 1], term.text):
                findings.append(Finding(file, line, column, term.text, term.key))
    return sorted(findings, key=lambda f: (f.file, f.line, f.column))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aip.modules.terms.lint", description="Report hard-coded labels."
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="repository root")
    parser.add_argument("--sources", type=Path, help="tree to scan (default: apps/api/aip)")
    parser.add_argument("--dictionary", type=Path, help="default: config/terms/en-AU")
    parser.add_argument("--allowlist", type=Path, help="default: config/terms/lint-allowlist.toml")
    parser.add_argument("--out", type=Path, help="write the findings JSON here")
    parser.add_argument("--report-only", action="store_true", help="exit 0 even with findings")
    args = parser.parse_args(argv)
    root: Path = args.root
    findings = scan(
        sources=args.sources or root / "apps" / "api" / "aip",
        dictionary=args.dictionary or root / "config" / "terms" / "en-AU",
        base=root,
        allowlist=args.allowlist or root / "config" / "terms" / "lint-allowlist.toml",
    )
    if args.out is not None:
        out: Path = args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps([asdict(f) for f in findings], indent=2) + "\n", encoding="utf-8")
    for f in findings:
        hint = f"use {f.suggested_key}" if f.suggested_key else "allow-list entry has no reason"
        print(f"{f.file}:{f.line}:{f.column}: raw label {f.term!r} ({hint})", file=sys.stderr)
    print(f"terms lint: {len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings and not args.report_only else 0


if __name__ == "__main__":
    sys.exit(main())
