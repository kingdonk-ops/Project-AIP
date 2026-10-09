"""TENANCY-02: only ``aip.platform.tenant_keys`` may build ``tenant:`` / ``tenants/`` keys.

Scans the AST of every file under ``aip/`` except the builders. A string constant (or the text
pieces of an f-string) containing ``tenant:`` or ``tenants/``, or equal to ``tenant-``/``tenant_``
(a prefix about to be concatenated with an id), is a hand-built key. Docstrings are exempt.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

AIP_DIR = Path(__file__).resolve().parents[2] / "aip"
BUILDERS = "platform/tenant_keys.py"

_HAND_BUILT = re.compile(r"tenant:|tenants/")
_DASHED_PREFIX = re.compile(r"^tenant[-_]$")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def violations(source: str, name: str = "<src>") -> list[str]:
    tree = ast.parse(source, filename=name)
    skip = _docstring_nodes(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip:
            continue
        text = node.value
        if _HAND_BUILT.search(text) or _DASHED_PREFIX.match(text):
            found.append(
                f"{name}:{node.lineno}: hand-built tenant key {text!r}; "
                "use aip.platform.tenant_keys"
            )
    return found


def scan(root: Path = AIP_DIR) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if rel == BUILDERS:
            continue
        found.extend(violations(path.read_text(encoding="utf-8"), rel))
    return found


def test_no_hand_built_tenant_keys() -> None:
    assert scan() == []


def test_checker_flags_literals_and_fstrings() -> None:
    assert len(violations('k = "tenant:abc:x"\n')) == 1
    assert len(violations('k = f"tenant:{t}:x"\n')) == 1
    assert len(violations('k = f"tenants/{t}/x"\n')) == 1
    assert len(violations('k = "a" + "tenants/" + t\n')) == 1
    assert len(violations('k = f"tenant-{t}-idx"\n')) == 1
    assert len(violations('p = "tenant_" + t\n')) == 1


def test_checker_ignores_builders_docstrings_and_slugs() -> None:
    ok = 'from aip.platform.tenant_keys import redis_key\nk = redis_key(t, "a")\n'
    assert violations(ok) == []
    assert violations('def f():\n    """Keys look like tenant:<id>."""\n') == []
    assert violations('slug = "tenant-b"\n') == []
