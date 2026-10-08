"""``aip-db lint``: static checks on every file in ``migrations/versions/`` (DATABASE-08).

Works on the Python AST and the SQL string literals of each revision. Rules:

- filename ``^\\d{12}_[a-z0-9_]+\\.py$`` and ``revision`` equal to the filename prefix;
- at module level only a docstring, imports, assignments, ``upgrade()`` and ``downgrade()``;
- ``downgrade()`` is exactly ``raise NotImplementedError("forward-only")``;
- ``upgrade()`` holds only ``op.execute(<str>)`` or ``op.execute(render_template(<literals>))``
  calls (the template is rendered and its SQL linted), plus
  ``with op.get_context().autocommit_block():`` around ``CREATE INDEX CONCURRENTLY``, one
  statement per ``op.execute``;
- no explicit ``BEGIN``/``COMMIT``, no session-level ``SET``, also inside dollar-quoted bodies;
  every ``set_config`` call has exactly the literal ``true`` as its third argument, and
  ``app.tenant_id`` is never set by ``SET``/``RESET`` or by
  ``ALTER ROLE``/``USER``/``DATABASE``/``SYSTEM``;
- ``DO`` blocks only in the baseline revision;
- ``CREATE EXTENSION`` only in the baseline (the revision with ``down_revision = None``);
- ``DROP TABLE``, ``DROP COLUMN`` (also ``ALTER TABLE ... DROP <column>``, where COLUMN is
  optional) and ``SET NOT NULL`` need ``# contract: <expand revision id>`` on the ``op.execute``
  call's lines or in the comment block just above it. So do the security-sensitive
  ``NO FORCE``/``DISABLE ROW LEVEL SECURITY``, ``GRANT aip_owner``, ``SECURITY DEFINER``,
  ``TRUNCATE`` and ``DROP SCHEMA``. They are found anywhere in the SQL, including dollar-quoted
  bodies, string literals (``EXECUTE 'DROP ...'``) and quoted identifiers;
- string literals may be standard (``'...'``), escape (``E'...'``) or dollar-quoted; quoted
  identifiers (``"..."``) are parsed so they cannot hide a comment marker;
- a single head;
- no revision modified or deleted relative to ``origin/main`` (merge base).
"""

from __future__ import annotations

import ast
import io
import re
import subprocess
import tokenize
from collections.abc import Iterator
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
MSG_AUTOCOMMIT_ONE = "autocommit_block allows one statement per op.execute"
MSG_MODULE = "only a docstring, imports, assignments, upgrade() and downgrade() may be top-level"
MSG_TEMPLATE = "template render failed"
MSG_SENSITIVE = "security-sensitive change needs a contract comment"
MSG_DO = "DO blocks are only allowed in the baseline revision"

_TRANSACTION_WORDS = ("BEGIN", "COMMIT", "ROLLBACK", "END", "ABORT", "START TRANSACTION")
_DESTRUCTIVE_RE = re.compile(r"\bDROP\s+TABLE\b|\bDROP\s+COLUMN\b|\bSET\s+NOT\s+NULL\b")
_ALTER_TABLE_RE = re.compile(r"\bALTER\s+TABLE\b")
# In ALTER TABLE, `DROP <name>` drops a column (COLUMN is optional); these DROPs do not.
_ALTER_TABLE_DROP_RE = re.compile(
    r"\bDROP\s+(?!CONSTRAINT\b|DEFAULT\b|IDENTITY\b|EXPRESSION\b|NOT\s+NULL\b)"
)
_SENSITIVE_RES = (
    re.compile(r"\bNO\s+FORCE\s+ROW\s+LEVEL\s+SECURITY\b"),
    re.compile(r"\bDISABLE\s+ROW\s+LEVEL\s+SECURITY\b"),
    re.compile(r"\bGRANT\s+(?:[A-Z0-9_]+\s*,\s*)*AIP_OWNER\b"),
    re.compile(r"\bSECURITY\s+DEFINER\b"),
    re.compile(r"\bTRUNCATE\b"),
    re.compile(r"\bDROP\s+SCHEMA\b"),
)
_TENANT_SET_RE = re.compile(
    r"\b(?:SET|RESET)\s+(?:SESSION\s+|LOCAL\s+)?APP\.TENANT_ID\b"
    r"|\bALTER\s+(?:ROLE|USER|DATABASE|SYSTEM)\b[^;]*\bAPP\.TENANT_ID\b"
)
_SET_CONFIG_CALL_RE = re.compile(r"\bSET_CONFIG\s*\(")
_EXTENSION_RE = re.compile(r"\bCREATE\s+EXTENSION\b")
_CONCURRENT_INDEX_RE = re.compile(r"^CREATE\s+(UNIQUE\s+)?INDEX\s+CONCURRENTLY\b")
_DOLLAR_TAG_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_BODY_SET_RE = re.compile(r"^(?:SET|RESET)\s|\b(?:BEGIN|THEN|ELSE|LOOP)\s+(?:SET|RESET)\s")
_IDENT_CHAR_RE = re.compile(r"[A-Za-z0-9_$]")
_TEMPLATE_FUNC = "render_template"


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


def _segments(sql: str) -> Iterator[tuple[str, str]]:
    """Split SQL into ``(kind, text)``: ``code``, ``comment``, ``string``, ``ident`` or ``dollar``.

    ``string`` covers ``'...'`` (``''`` escapes a quote) and ``E'...'`` (a backslash escapes the
    next character too); ``ident`` is a quoted identifier ``"..."`` (``""`` escapes a quote);
    ``dollar`` is a whole ``$tag$ ... $tag$`` including both tags.
    """
    i, n, start = 0, len(sql), 0
    while i < n:
        ch = sql[i]
        after_ident = i > 0 and bool(_IDENT_CHAR_RE.match(sql[i - 1]))
        kind, end = "", i
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            kind, end = "comment", (n if end == -1 else end)
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            kind, end = "comment", (n if end == -1 else end + 2)
        elif ch == "$" and not after_ident and (m := _DOLLAR_TAG_RE.match(sql, i)):
            close = sql.find(m.group(0), m.end())
            kind, end = "dollar", (n if close == -1 else close + len(m.group(0)))
        elif ch == "'" or (ch in "eE" and sql.startswith("'", i + 1) and not after_ident):
            backslash = ch != "'"
            j = i + (2 if backslash else 1)
            while j < n:
                if backslash and sql[j] == "\\":
                    j += 2
                    continue
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            kind, end = "string", min(j + 1, n)
        elif ch == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            kind, end = "ident", min(j + 1, n)
        if not kind:
            i += 1
            continue
        if i > start:
            yield "code", sql[start:i]
        yield kind, sql[i:end]
        i = start = end
    if n > start:
        yield "code", sql[start:n]


def strip_sql(sql: str) -> str:
    """Blank out comments, dollar-quoted bodies, string literals and quoted identifiers.

    Literals become ``''`` and quoted identifiers ``"_"``, so statements keep their shape.
    """
    blanks = {"comment": " ", "dollar": " '' ", "string": "''", "ident": '"_"'}
    return "".join(blanks.get(kind, text) for kind, text in _segments(sql))


def strip_comments(sql: str) -> str:
    """Blank out comments only: string literals and dollar-quoted bodies are kept."""
    return "".join(" " if kind == "comment" else text for kind, text in _segments(sql))


def dollar_bodies(sql: str) -> list[str]:
    """The bodies of the top-level dollar-quoted strings, without their tags."""
    bodies: list[str] = []
    for kind, text in _segments(sql):
        if kind != "dollar":
            continue
        tag = _DOLLAR_TAG_RE.match(text)
        size = len(tag.group(0)) if tag else 0
        closed = len(text) >= 2 * size and text.endswith(text[:size])
        bodies.append(text[size : len(text) - size] if closed else text[size:])
    return bodies


def sql_statements(sql: str) -> list[str]:
    """Upper-cased, whitespace-normalised statements with comments and literals blanked."""
    parts = strip_sql(sql).split(";")
    return [" ".join(p.split()).upper() for p in parts if p.strip()]


def _body_has_session_set(body: str) -> bool:
    """A ``SET``/``RESET`` statement inside a dollar-quoted (PL/pgSQL) body, at any depth."""
    if any(_BODY_SET_RE.search(stmt) for stmt in sql_statements(body)):
        return True
    return any(_body_has_session_set(inner) for inner in dollar_bodies(body))


def _call_args(code: str, start: int) -> list[str] | None:
    """Top-level arguments of the call whose ``(`` ends just before ``start``; None if unclosed."""
    args: list[str] = []
    depth, quote, i, arg_start = 0, "", start, start
    while i < len(code):
        ch = code[i]
        if quote:
            if ch == quote:
                if code.startswith(quote, i + 1):  # '' or "" escape
                    i += 2
                    continue
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                args.append(code[arg_start:i].strip())
                return args
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(code[arg_start:i].strip())
            arg_start = i + 1
        i += 1
    return None


def _bad_set_config(code: str) -> bool:
    """Any ``set_config`` call whose third argument is not exactly the literal ``true``."""
    for m in _SET_CONFIG_CALL_RE.finditer(code):
        args = _call_args(code, m.end())
        if args is None or len(args) != 3 or args[2] != "TRUE":
            return True
    return False


def _destructive(code: str) -> bool:
    if _DESTRUCTIVE_RE.search(code):
        return True
    return any(
        _ALTER_TABLE_RE.search(stmt) and _ALTER_TABLE_DROP_RE.search(stmt)
        for stmt in code.split(";")
    )


def _sql_findings(sql: str, *, is_baseline: bool, has_contract: bool) -> list[str]:
    found: list[str] = []
    for stmt in sql_statements(sql):
        if any(stmt == w or stmt.startswith(w + " ") for w in _TRANSACTION_WORDS):
            found.append(MSG_TRANSACTION)
        if stmt.startswith(("SET ", "RESET ")):
            found.append(MSG_SET)
        if (stmt == "DO" or stmt.startswith("DO ")) and not is_baseline:
            found.append(MSG_DO)
    if any(_body_has_session_set(body) for body in dollar_bodies(sql)):
        found.append(MSG_SET)
    # Everything but comments: DO bodies, EXECUTE '...' strings and quoted names cannot hide
    # these. `code` keeps quotes (for set_config argument parsing); `bare` drops `"`.
    code = " ".join(strip_comments(sql).split()).upper()
    bare = code.replace('"', "")
    if _bad_set_config(code) or _TENANT_SET_RE.search(bare):
        found.append(MSG_SET)
    if _EXTENSION_RE.search(bare) and not is_baseline:
        found.append(MSG_EXTENSION)
    if not has_contract:
        if _destructive(bare):
            found.append(MSG_CONTRACT)
        if any(rx.search(bare) for rx in _SENSITIVE_RES):
            found.append(MSG_SENSITIVE)
    return list(dict.fromkeys(found))


class _TemplateFailedError(Exception):
    pass


def _render_call(call: ast.Call) -> str | None:
    """The SQL of ``render_template("<name>", key="<literal>", ...)``, or None if not literal."""
    from aip.platform.db.errors import TemplateError
    from aip.platform.db.templates import render_template

    if not (isinstance(call.func, ast.Name) and call.func.id == _TEMPLATE_FUNC):
        return None
    if len(call.args) != 1:
        return None
    name = call.args[0]
    if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
        return None
    variables: dict[str, object] = {}
    for kw in call.keywords:
        if kw.arg is None or not isinstance(kw.value, ast.Constant):
            return None
        if not isinstance(kw.value.value, str):
            return None
        variables[kw.arg] = kw.value.value
    try:
        return render_template(name.value, **variables)
    except TemplateError as exc:
        raise _TemplateFailedError(str(exc)) from exc


def _execute_sql(stmt: ast.stmt) -> str | None:
    """The SQL of ``op.execute("<literal>")`` or ``op.execute(render_template(...))``, else None.

    Raises ``_TemplateFailedError`` when a literal ``render_template`` call cannot be rendered.
    """
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
    if isinstance(arg, ast.Call):
        return _render_call(arg)
    return None


def _comment_lines(source: str) -> dict[int, str]:
    """Line number -> Python comment text (from ``tokenize``, so never inside a string)."""
    comments: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.string
    except (tokenize.TokenError, SyntaxError):
        pass
    return comments


def _has_contract(node: ast.stmt, comments: dict[int, str], lines: list[str]) -> bool:
    """A ``# contract: <rev>`` on the call's own lines or in the comment block right above it."""
    end = node.end_lineno or node.lineno
    if any(CONTRACT_RE.search(comments.get(n, "")) for n in range(node.lineno, end + 1)):
        return True
    n = node.lineno - 1
    while n >= 1 and lines[n - 1].lstrip().startswith("#"):
        if CONTRACT_RE.search(comments.get(n, "")):
            return True
        n -= 1
    return False


_MODULE_STMTS = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)


def _module_findings(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for index, stmt in enumerate(tree.body):
        if isinstance(stmt, _MODULE_STMTS):
            continue
        if isinstance(stmt, ast.FunctionDef) and stmt.name in ("upgrade", "downgrade"):
            continue
        is_docstring = (
            index == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
        if not is_docstring:
            found.append((stmt.lineno, MSG_MODULE))
    return found


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

    for line, message in _module_findings(tree):
        add(line, message)
    comments = _comment_lines(source)
    lines = source.splitlines()
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
        contract = _has_contract(stmt, comments, lines)
        for message in _sql_findings(sql, is_baseline=rev.is_baseline, has_contract=contract):
            add(stmt.lineno, message)

    def execute_sql(stmt: ast.stmt) -> str | None:
        try:
            return _execute_sql(stmt)
        except _TemplateFailedError as exc:
            add(stmt.lineno, f"{MSG_TEMPLATE}: {exc}")
            return ""

    for stmt in _without_docstring(upgrade.body):
        sql = execute_sql(stmt)
        if sql is not None:
            check_sql(stmt, sql)
        elif _is_autocommit_block(stmt):
            assert isinstance(stmt, ast.With)
            for inner in stmt.body:
                inner_sql = execute_sql(inner)
                if inner_sql is None:
                    add(inner.lineno, MSG_ONLY_EXECUTE)
                    continue
                statements = sql_statements(inner_sql)
                if len(statements) > 1:
                    add(inner.lineno, MSG_AUTOCOMMIT_ONE)
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
