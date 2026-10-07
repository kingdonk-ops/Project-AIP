"""``aip-db``: migrate, new, lint, snapshot, check-schema (DATABASE-08). No downgrade command."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import MetaData

from aip.platform.db.migrator import (
    alembic_ini,
    api_dir,
    lint,
    new,
    run,
    schema_check,
    snapshot,
    snapshot_path,
    versions_dir,
)


def load_declared_tables() -> MetaData:
    """The shared ``MetaData`` after importing every module's ``tables.py``.

    Modules are found by directory name and imported dynamically, so the platform holds no
    static import of ``aip.modules`` (ADR 0004). The ARCH-02 registry can replace this scan.
    """
    from aip.platform.db.metadata import metadata

    modules_dir = api_dir() / "aip" / "modules"
    if modules_dir.is_dir():
        for path in sorted(modules_dir.iterdir()):
            if path.name.startswith(("_", ".")) or not (path / "tables.py").is_file():
                continue
            importlib.import_module(f"aip.modules.{path.name}.tables")
    return metadata


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aip-db", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate", help="alembic upgrade head as aip_owner")
    migrate.add_argument("--config", type=Path, default=None, help="alembic.ini path")

    new_cmd = sub.add_parser("new", help="create a blank forward-only revision")
    new_cmd.add_argument("slug")
    new_cmd.add_argument("--config", type=Path, default=None, help="alembic.ini path")

    lint_cmd = sub.add_parser("lint", help="lint migrations/versions/")
    lint_cmd.add_argument("--versions-dir", type=Path, default=None)
    lint_cmd.add_argument("--base", default="origin/main", help="git ref revisions must match")
    lint_cmd.add_argument("--no-git", action="store_true", help="skip the immutability check")

    snap = sub.add_parser("snapshot", help="write the normalised schema-only dump")
    snap.add_argument("--output", type=Path, default=None)

    sub.add_parser("check-schema", help="compare the migrated schema with the declared tables")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "migrate":
            return _migrate(args.config or alembic_ini())
        if args.command == "new":
            path = new.create_revision(args.slug, config_path=args.config or alembic_ini())
            print(path)
            return 0
        if args.command == "lint":
            return _lint(args.versions_dir or versions_dir(), None if args.no_git else args.base)
        if args.command == "snapshot":
            out = snapshot.write_snapshot(run.migrator_url(), args.output or snapshot_path())
            print(f"wrote {out}")
            return 0
        if args.command == "check-schema":
            return schema_check.check_schema(run.migrator_url(), load_declared_tables())
    except (run.MigratorError, new.InvalidSlugError, new.RevisionExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    raise AssertionError(f"unhandled command {args.command}")


def _migrate(config: Path) -> int:
    try:
        run.migrate(config)
    except run.MigratorError:
        raise
    except Exception as exc:
        print(f"migration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


def _lint(directory: Path, base: str | None) -> int:
    findings = lint.lint_directory(directory, git_base=base)
    for finding in findings:
        print(finding)
    if not findings:
        print(f"{directory}: migrations lint clean")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
