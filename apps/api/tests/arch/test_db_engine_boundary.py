"""DATABASE-02 / ADR 0002: only ``aip.platform.db`` creates database engines or connections.

Everything else gets its connection from ``with_tenant``, so every query runs with the tenant
set. This scans the AST of every file under ``aip/`` outside ``aip/platform/db/``.

ARCH-03's import-linter cannot express this: it sees ``sqlalchemy`` and ``asyncpg`` only as whole
packages, and modules legitimately import ``sqlalchemy`` for ``Table``/``select`` in
``tables.py`` and ``repository.py``.

DATABASE-07: aliased imports (``import asyncpg as pg``) are resolved, and opening a connection
straight off a platform engine (``get_engine().connect()`` / ``.begin()``) also counts, since it
skips ``with_tenant``.
"""

from __future__ import annotations

import ast
from pathlib import Path

AIP_DIR = Path(__file__).resolve().parents[2] / "aip"
DB_DIR = AIP_DIR / "platform" / "db"

# Names that build an engine, a pool or a raw connection.
FACTORIES = frozenset(
    {
        "create_engine",
        "create_async_engine",
        "engine_from_config",
        "async_engine_from_config",
        "create_mock_engine",
        "AsyncEngine",
        "Engine",
        "create_pool",
        "connect",
    }
)
RAW_DRIVERS = frozenset({"asyncpg", "psycopg", "psycopg2", "sqlalchemy"})
# The platform's engine getters: a connection opened straight off one skips with_tenant.
ENGINE_GETTERS = frozenset({"get_engine", "get_jobs_engine", "get_audit_writer_engine"})
ENGINE_OPENERS = frozenset({"connect", "begin"})

# Two probes open one short, time-limited asyncpg connection each and read no tenant data, so
# they must work while the app engine is unhealthy: the OPS-04 readiness probe (`select 1` and
# the applied Alembic revision) and the STACK-05 version endpoint (`SHOW server_version`).
# These are the only exceptions.
ALLOWED = {
    ("modules/ops/health.py", "asyncpg.connect"),
    ("platform/version/routes.py", "asyncpg.connect"),
    # The worker's startup check opens one aip_jobs connection so a privileged login stops it
    # before any job runs; it reads nothing.
    ("worker.py", "get_jobs_engine().connect"),
}


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def _aliases(tree: ast.AST) -> dict[str, str]:
    """``import asyncpg as pg`` -> ``{pg: asyncpg}``; ``from sqlalchemy import ext as e`` too."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    out[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.asname and alias.name not in FACTORIES:  # getters resolve through it
                    out[alias.asname] = f"{node.module}.{alias.name}"
    return out


def _getter(call: ast.expr, aliases: dict[str, str]) -> str | None:
    """The platform engine getter ``call`` invokes (aliased or module-qualified), or ``None``."""
    if not isinstance(call, ast.Call):
        return None
    func = call.func
    if isinstance(func, ast.Name):
        name = aliases.get(func.id, func.id).rpartition(".")[2]
    elif isinstance(func, ast.Attribute):
        name = func.attr
    else:
        return None
    return name if name in ENGINE_GETTERS else None


def _engine_names(tree: ast.AST, aliases: dict[str, str]) -> dict[str, str]:
    """Names bound to a platform engine (``e = get_engine()``), mapped to the getter."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        getter = _getter(value, aliases)
        if getter is not None:
            out.update({t.id: getter for t in targets if isinstance(t, ast.Name)})
    return out


def _engine_opener(node: ast.Call, aliases: dict[str, str], engines: dict[str, str]) -> str | None:
    """``get_engine().connect`` for ``get_engine().connect()`` (also through an alias, a module
    or a variable holding the engine), else ``None``."""
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in ENGINE_OPENERS):
        return None
    getter = _getter(func.value, aliases)
    if getter is None and isinstance(func.value, ast.Name):
        getter = engines.get(func.value.id)
    return None if getter is None else f"{getter}().{func.attr}"


def violations(path: Path, root: Path = AIP_DIR) -> list[str]:
    rel = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _aliases(tree)
    engines = _engine_names(tree, aliases)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            for alias in node.names:
                if top in RAW_DRIVERS and alias.name in FACTORIES:
                    found.append(f"{rel}:{node.lineno}: imports {node.module}.{alias.name}")
        elif isinstance(node, ast.Call):
            opener = _engine_opener(node, aliases, engines)
            if opener is not None:
                if (rel, opener) not in ALLOWED:
                    found.append(f"{rel}:{node.lineno}: calls {opener}")
                continue
            name = _dotted(node.func)
            if name is None:
                continue
            first, dot, rest = name.partition(".")
            if first in aliases:
                name = f"{aliases[first]}{dot}{rest}"
            head, _, last = name.rpartition(".")
            if last not in FACTORIES or head.split(".")[0] not in RAW_DRIVERS:
                continue
            if (rel, name) not in ALLOWED:
                found.append(f"{rel}:{node.lineno}: calls {name}")
    return found


def test_nothing_outside_platform_db_creates_an_engine_or_connection() -> None:
    files = [
        p
        for p in sorted(AIP_DIR.rglob("*.py"))
        if DB_DIR not in p.parents and "__pycache__" not in p.parts
    ]
    assert files, "no sources found"
    offenders = [v for path in files for v in violations(path)]
    assert offenders == []


def test_the_scan_catches_engine_and_connection_factories(tmp_path: Path) -> None:
    fixture = tmp_path / "modules" / "x.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        "import asyncpg\n"
        "from sqlalchemy.ext.asyncio import create_async_engine\n"
        "import sqlalchemy\n"
        "e = sqlalchemy.create_engine('postgresql://x')\n"
        "c = asyncpg.connect('postgresql://x')\n"
        "p = asyncpg.create_pool('postgresql://x')\n"
        "from sqlalchemy import select, Table\n",
        encoding="utf-8",
    )
    assert violations(fixture, root=tmp_path) == [
        "modules/x.py:2: imports sqlalchemy.ext.asyncio.create_async_engine",
        "modules/x.py:4: calls sqlalchemy.create_engine",
        "modules/x.py:5: calls asyncpg.connect",
        "modules/x.py:6: calls asyncpg.create_pool",
    ]


def test_the_scan_resolves_aliases_and_engine_openers(tmp_path: Path) -> None:
    fixture = tmp_path / "modules" / "y.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        "import asyncpg as pg\n"
        "import sqlalchemy as sa\n"
        "from aip.platform.db.engine import get_engine\n"
        "c = pg.connect('postgresql://x')\n"
        "e = sa.create_engine('postgresql://x')\n"
        "async def f():\n"
        "    async with get_engine().connect() as conn:\n"
        "        pass\n"
        "    async with get_engine().begin() as conn:\n"
        "        pass\n",
        encoding="utf-8",
    )
    assert violations(fixture, root=tmp_path) == [
        "modules/y.py:4: calls asyncpg.connect",
        "modules/y.py:5: calls sqlalchemy.create_engine",
        "modules/y.py:7: calls get_engine().connect",
        "modules/y.py:9: calls get_engine().begin",
    ]


def test_the_scan_follows_aliased_qualified_and_stored_engines(tmp_path: Path) -> None:
    fixture = tmp_path / "modules" / "z.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        "from aip.platform.db import engine\n"
        "from aip.platform.db.engine import get_engine as ge\n"
        "async def f():\n"
        "    async with ge().connect() as c:\n"
        "        pass\n"
        "    async with engine.get_jobs_engine().begin() as c:\n"
        "        pass\n"
        "    e = ge()\n"
        "    async with e.connect() as c:\n"
        "        pass\n",
        encoding="utf-8",
    )
    assert violations(fixture, root=tmp_path) == [
        "modules/z.py:4: calls get_engine().connect",
        "modules/z.py:6: calls get_jobs_engine().begin",
        "modules/z.py:9: calls get_engine().connect",
    ]
