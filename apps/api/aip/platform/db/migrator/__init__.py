"""``aip-db``: forward-only migrator, migration lint, schema snapshot and check (DATABASE-08).

Paths default to the source checkout; the migrator image overrides them with ``AIP_ALEMBIC_INI``
and ``AIP_REPO_ROOT``.
"""

import os
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[4]


def api_dir() -> Path:
    """``apps/api`` (holds ``alembic.ini`` and ``migrations/``)."""
    ini = os.environ.get("AIP_ALEMBIC_INI")
    return Path(ini).resolve().parent if ini else _API_DIR


def alembic_ini() -> Path:
    return Path(os.environ.get("AIP_ALEMBIC_INI") or _API_DIR / "alembic.ini")


def repo_root() -> Path:
    root = os.environ.get("AIP_REPO_ROOT")
    return Path(root) if root else _API_DIR.parents[1]


def versions_dir() -> Path:
    return api_dir() / "migrations" / "versions"


def snapshot_path() -> Path:
    return repo_root() / "db" / "schema.snapshot.sql"
