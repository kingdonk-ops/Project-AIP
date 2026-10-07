"""``aip-db new <slug>``: render a blank forward-only revision from ``script.py.mako``.

The revision id is the current UTC time ``YYYYMMDDHHMM``. Tenant-table and append-only SQL
templates live in ``db/templates/`` (DATABASE-02, AUDIT-01).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
MAX_SLUG = 60  # alembic.ini truncate_slug_length


class InvalidSlugError(ValueError):
    pass


class RevisionExistsError(FileExistsError):
    pass


def create_revision(slug: str, *, config_path: Path, now: datetime | None = None) -> Path:
    """Create ``<YYYYMMDDHHMM>_<slug>.py`` and return its path; never overwrites."""
    if not SLUG_RE.match(slug) or len(slug) > MAX_SLUG:
        raise InvalidSlugError(
            f"invalid slug {slug!r}: use snake_case up to {MAX_SLUG} chars, e.g. add_widgets"
        )
    rev_id = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%d%H%M")
    config = Config(str(config_path))
    versions = Path(ScriptDirectory.from_config(config).versions)
    clash = sorted(p.name for p in versions.glob(f"{rev_id}_*.py"))
    if clash:
        raise RevisionExistsError(f"revision {rev_id} already exists ({clash[0]}); retry later")
    script = command.revision(config, message=slug, rev_id=rev_id)
    if script is None or isinstance(script, list):
        raise RuntimeError("alembic did not create a revision")
    return Path(script.path)
