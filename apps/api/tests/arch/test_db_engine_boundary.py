"""DATABASE-02 / ADR 0002: only ``aip.platform.db`` creates database engines or connections.

Everything else gets its connection from ``with_tenant``, so every query runs with the tenant
set. This scans the AST of every file under ``aip/`` outside ``aip/platform/db/``.

ARCH-03's import-linter cannot express this: it sees ``sqlalchemy`` and ``asyncpg`` only as whole
packages, and modules legitimately import ``sqlalchemy`` for ``Table``/``select`` in
``tables.py`` and ``repository.py``.
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

# Two probes open one short, time-limited asyncpg connection each and read no tenant data, so
# they must work while the app engine is unhealthy: the OPS-04 readiness probe (`select 1` and
# the applied Alembic revision) and the STACK-05 version endpoint (`SHOW server_version`).
# These are the only exceptions.
ALLOWED = {
    ("modules/ops/health.py", "asyncpg.connect"),
    ("platform/version/routes.py", "asyncpg.connect"),
}


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def violations(path: Path, root: Path = AIP_DIR) -> list[str]:
    rel = path.relative_to(root).as_posix()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            for alias in node.names:
                if top in RAW_DRIVERS and alias.name in FACTORIES:
                    found.append(f"{rel}:{node.lineno}: imports {node.module}.{alias.name}")
        elif isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name is None:
                continue
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
