"""``aip-db lint``: static checks on every file in ``migrations/versions/`` (DATABASE-08).

Works on the Python AST and the SQL string literals of each revision. Rules:

- filename ``^\\d{12}_[a-z0-9_]+\\.py$`` and ``revision`` equal to the filename prefix;
- ``downgrade()`` is exactly ``raise NotImplementedError("forward-only")``;
- ``upgrade()`` holds only ``op.execute(<str>)`` calls, plus
  ``with op.get_context().autocommit_block():`` around ``CREATE INDEX CONCURRENTLY``;
- no explicit ``BEGIN``/``COMMIT``, no session-level ``SET`` (only ``set_config(..., true)``);
- ``CREATE EXTENSION`` only in the baseline (the revision with ``down_revision = None``);
- ``DROP TABLE``, ``DROP COLUMN`` and ``SET NOT NULL`` need ``# contract: <expand revision id>``;
- a single head;
- no revision modified or deleted relative to ``origin/main`` (merge base).
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

FILENAME_RE = re.compile(r"^\d{12}_[a-z0-9_]+\.py$")
CONTRACT_RE = re.compile(r"#\s*contract:\s*\d{12}\b")

MSG_FILENAME = "invalid migration filename"
MSG_DOWNGRADE = "downgrades are not allowed"
MSG_ONLY_EXECUTE = "only op.execute(raw SQL) is allowed"
MSG_AUTOCOMMIT = "autocommit_block is only allowed around CREATE INDEX CONCURRENTLY"
MSG_TRANSACTION = "explicit transaction control (BEGIN/COMMIT) is forbidden"
MSG_SET = "session-level SET is forbidden; use set_config(..., true)"
MSG_EXTENSION = "CREATE EXTENSION is only allowed in the baseline revision"
MSG_CONTRACT = "destructive change needs a contract comment"

_TRANSACTION_WORDS = ("BEGIN", "COMMIT", "ROLLBACK", "END", "ABORT", "START TRANSACTION")
_DESTRUCTIVE_RE = re.compile(r"\bDROP\s+TABLE\b|\bDROP\s+COLUMN\b|\bSET\s+NOT\s+NULL\b")
_EXTENSION_RE = re.compile(r"\bCREATE\s+EXTENSION\b")
_SET_CONFIG_FALSE_RE = re.compile(r"\bSET_CONFIG\s*\([^)]*,\s*FALSE\s*\)")
_CONCURRENT_INDEX_RE = re.compile(r"^CREATE\s+(UNIQUE\s+)?INDEX\s+CONCURRENTLY\b")
_DOLLAR_TAG_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


@dataclass
class _Revision:
    path: Path
    revision: str | None = None
    down_revisions: tuple[str, ...] = ()
    is_baseline: bool = False
    findings: list[Finding] = field(default_factory=list[Finding])


def strip_sql(sql: str) -> str:
    """Blank out comments, dollar-quoted bodies and string literals (keeps ``''`` placeholders)."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
        elif ch == "$" and (m := _DOLLAR_TAG_RE.match(sql, i)):
            tag = m.group(0)
            end = sql.find(tag, m.end())
            i = n if end == -1 else end + len(tag)
            out.append(" '' ")
        elif ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            out.append("''")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def sql_statements(sql: str) -> list[str]:
    """Upper-cased, whitespace-normalised statements with comments and literals blanked."""
    parts = strip_sql(sql).split(";")
    return [" ".join(p.split()).upper() for p in parts if p.strip()]


def _sql_findings(sql: str, *, is_baseline: bool, has_contract: bool) -> list[str]:
    found: list[str] = []
    for stmt in sql_statements(sql):
        if any(stmt == w or stmt.startswith(w + " ") for w in _TRANSACTION_WORDS):
            found.append(MSG_TRANSACTION)
        if stmt.startswith(("SET ", "RESET ")) or _SET_CONFIG_FALSE_RE.search(stmt):
            found.append(MSG_SET)
        if _EXTENSION_RE.search(stmt) and not is_baseline:
            found.append(MSG_EXTENSION)
        if _DESTRUCTIVE_RE.search(stmt) and not has_contract:
            found.append(MSG_CONTRACT)
    return found


def _execute_sql(stmt: ast.stmt) -> str | None:
    """The SQL of ``op.execute("<literal>")``, or None for anything else."""
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    func = call.func
    if not (
        isinstance(func, ast.Attribute)
        and func.attr == "execute"
        and isinstance(func.value, ast.Name)
        and func.value.id == "op"
    ):
        return None
    if call.keywords or len(call.args) != 1:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _is_autocommit_block(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.With) or len(stmt.items) != 1:
        return False
    expr = stmt.items[0].context_expr
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "autocommit_block"
        and isinstance(expr.func.value, ast.Call)
        and isinstance(expr.func.value.func, ast.Attribute)
        and expr.func.value.func.attr == "get_context"
        and isinstance(expr.func.value.func.value, ast.Name)
        and expr.func.value.func.value.id == "op"
    )


def _without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    first = body[0] if body else None
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return body[1:]
    return body


def _is_forward_only_raise(body: list[ast.stmt]) -> bool:
    stmts = _without_docstring(body)
    if len(stmts) != 1 or not isinstance(stmts[0], ast.Raise):
        return False
    exc = stmts[0].exc
    return (
        isinstance(exc, ast.Call)
        and isinstance(exc.func, ast.Name)
        and exc.func.id == "NotImplementedError"
        and not exc.keywords
        and len(exc.args) == 1
        and isinstance(exc.args[0], ast.Constant)
        and exc.args[0].value == "forward-only"
        and stmts[0].cause is None
    )


def _string_or_none(node: ast.expr) -> tuple[bool, tuple[str, ...]]:
    """Parse a ``down_revision`` value: (ok, revisions)."""
    if isinstance(node, ast.Constant) and node.value is None:
        return True, ()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True, (node.value,)
    if isinstance(node, ast.Tuple | ast.List):
        values = [e.value for e in node.elts if isinstance(e, ast.Constant)]
        if len(values) == len(node.elts) and all(isinstance(v, str) for v in values):
            return True, tuple(str(v) for v in values)
    return False, ()


def _module_assignments(tree: ast.Module) -> dict[str, tuple[int, ast.expr]]:
    found: dict[str, tuple[int, ast.expr]] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                found[target.id] = (stmt.lineno, stmt.value)
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.value is not None
        ):
            found[stmt.target.id] = (stmt.lineno, stmt.value)
    return found


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {s.name: s for s in tree.body if isinstance(s, ast.FunctionDef)}


def lint_file(path: Path) -> _Revision:
    """Lint one revision file; the result carries its findings and graph edges."""
    rev = _Revision(path=path)
    name = str(path)

    def add(line: int, message: str) -> None:
        rev.findings.append(Finding(name, line, message))

    if not FILENAME_RE.match(path.name):
        add(1, MSG_FILENAME)
        return rev

    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=name)
    except SyntaxError as exc:
        add(exc.lineno or 1, f"cannot parse: {exc.msg}")
        return rev

    prefix = path.name[:12]
    assigns = _module_assignments(tree)
    if "revision" not in assigns:
        add(1, "missing revision")
    else:
        line, node = assigns["revision"]
        value = node.value if isinstance(node, ast.Constant) else None
        if not isinstance(value, str):
            add(line, "revision must be a string literal")
        else:
            rev.revision = value
            if value != prefix:
                add(line, f"revision {value} does not match filename prefix {prefix}")
    if "down_revision" not in assigns:
        add(1, "missing down_revision")
    else:
        line, node = assigns["down_revision"]
        ok, downs = _string_or_none(node)
        if not ok:
            add(line, "down_revision must be None, a string or a tuple of strings")
        rev.down_revisions = downs
        rev.is_baseline = ok and not downs

    has_contract = bool(CONTRACT_RE.search(source))
    functions = _functions(tree)

    downgrade = functions.get("downgrade")
    if downgrade is None:
        add(1, "missing downgrade()")
    elif not _is_forward_only_raise(downgrade.body):
        add(downgrade.lineno, MSG_DOWNGRADE)

    upgrade = functions.get("upgrade")
    if upgrade is None:
        add(1, "missing upgrade()")
        return rev

    def check_sql(stmt: ast.stmt, sql: str) -> None:
        for message in _sql_findings(sql, is_baseline=rev.is_baseline, has_contract=has_contract):
            add(stmt.lineno, message)

    for stmt in _without_docstring(upgrade.body):
        sql = _execute_sql(stmt)
        if sql is not None:
            check_sql(stmt, sql)
        elif _is_autocommit_block(stmt):
            assert isinstance(stmt, ast.With)
            for inner in stmt.body:
                inner_sql = _execute_sql(inner)
                if inner_sql is None:
                    add(inner.lineno, MSG_ONLY_EXECUTE)
                    continue
                statements = sql_statements(inner_sql)
                if not statements or not all(_CONCURRENT_INDEX_RE.match(s) for s in statements):
                    add(inner.lineno, MSG_AUTOCOMMIT)
                check_sql(inner, inner_sql)
        else:
            add(stmt.lineno, MSG_ONLY_EXECUTE)
    return rev


def _head_findings(versions_dir: Path, revisions: list[_Revision]) -> list[Finding]:
    known = {r.revision for r in revisions if r.revision}
    referenced = {d for r in revisions for d in r.down_revisions}
    heads = sorted(known - referenced)
    if len(heads) > 1:
        return [Finding(str(versions_dir), 0, f"multiple heads: {', '.join(heads)}")]
    return []


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _git_findings(versions_dir: Path, base: str) -> list[Finding]:
    """Revisions are immutable once merged: flag files modified or deleted since the merge base."""
    where = str(versions_dir)
    merge_base = _git(versions_dir, "merge-base", base, "HEAD")
    if merge_base.returncode != 0:
        detail = (merge_base.stderr.strip() or "no merge base").splitlines()[0]
        return [Finding(where, 0, f"cannot diff against {base}: {detail}")]
    diff = _git(
        versions_dir, "diff", "--name-status", "--no-renames", merge_base.stdout.strip(), "--", "."
    )
    if diff.returncode != 0:
        return [Finding(where, 0, f"cannot diff against {base}: {diff.stderr.strip()}")]
    findings: list[Finding] = []
    for line in diff.stdout.splitlines():
        status, _, file = line.partition("\t")
        if status.startswith("D"):
            findings.append(Finding(file, 0, f"applied revision deleted relative to {base}"))
        elif status.startswith(("M", "T")):
            findings.append(Finding(file, 0, f"applied revision modified relative to {base}"))
    return findings


def lint_directory(versions_dir: Path, *, git_base: str | None = "origin/main") -> list[Finding]:
    """Lint every file in ``versions_dir``; ``git_base=None`` skips the immutability check."""
    files = sorted(p for p in versions_dir.iterdir() if p.is_file())
    revisions = [lint_file(p) for p in files]
    findings = [f for r in revisions for f in r.findings]
    findings += _head_findings(versions_dir, [r for r in revisions if r.revision])
    if git_base is not None:
        findings += _git_findings(versions_dir, git_base)
    return findings
