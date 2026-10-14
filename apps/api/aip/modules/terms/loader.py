"""Load the platform default dictionary into ``term_key`` (TERMS-01).

    DATABASE_MIGRATOR_URL=... python -m aip.modules.terms.loader config/terms/en-AU

Runs in the deploy migrate job right after ``aip-db migrate``. The directory name is the default
locale; each ``<module>.json`` file holds that module's keys as
``{"<key>": {"text": "<ICU message>", "description": "<translator context>"}}``. A bare string
value (``{"<key>": "<ICU message>"}``, the form the earlier shell files use) is the text with no
description.

Every file is read and validated before anything is written: each text must parse as ICU
MessageFormat and must not be an internal code (a snake_case code or the key itself). One bad
entry aborts the whole load with an error naming the key and file.

Rows are upserted by key as ``aip_owner`` with the platform tenant bound
(``with_platform_tenant``), in one transaction. A row is rewritten only when its module, text or
description changed, so a re-run reports every key unchanged. Keys removed from the files are
left in place (removing a key is a later, reviewed change).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pyicumessageformat import Parser  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import text

from aip.platform.context import new_request_id
from aip.platform.db.migrator.run import create_migrator_engine
from aip.platform.db.session import PLATFORM_TENANT_ID, with_platform_tenant

__all__ = [
    "DictionaryError",
    "InvalidMessageError",
    "LoadResult",
    "TermEntry",
    "load",
    "main",
    "read_dictionary",
]

URL_ENV = "DATABASE_MIGRATOR_URL"
# Dotted, lower-case first segment; later segments may be camelCase or kebab-case (the shell
# files use both, e.g. ``shell.nav.section.my-work``).
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[A-Za-z0-9_-]+)+$")
_MODULE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
# An internal status or workflow code (two or more snake_case words) must never be display text.
_INTERNAL_CODE_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")

_UPSERT = text(
    """
    INSERT INTO term_key (id, tenant_id, key, module_id, default_locale, default_text, description)
    VALUES (:id, :tenant_id, :key, :module_id, :locale, :text, :description)
    ON CONFLICT (key) DO UPDATE
      SET module_id = EXCLUDED.module_id,
          default_locale = EXCLUDED.default_locale,
          default_text = EXCLUDED.default_text,
          description = EXCLUDED.description,
          deleted_at = NULL,
          updated_at = now()
      WHERE (term_key.module_id, term_key.default_locale, term_key.default_text,
             term_key.description, term_key.deleted_at IS NULL)
            IS DISTINCT FROM
            (EXCLUDED.module_id, EXCLUDED.default_locale, EXCLUDED.default_text,
             EXCLUDED.description, true)
    RETURNING (xmax = 0) AS inserted
    """
)


class DictionaryError(ValueError):
    """A dictionary directory or file is malformed; nothing was written."""


class InvalidMessageError(DictionaryError):
    """One entry's text is not a valid display message; nothing was written."""

    def __init__(self, key: str, file: Path, reason: str) -> None:
        super().__init__(f"{file.name}: {key}: {reason}")
        self.key = key
        self.file = file
        self.reason = reason


@dataclass(frozen=True, slots=True)
class TermEntry:
    key: str
    module_id: str
    locale: str
    text: str
    description: str | None
    file: Path


@dataclass(frozen=True, slots=True)
class LoadResult:
    inserted: int
    updated: int
    unchanged: int


def _check_message(key: str, file: Path, message: str, parser: Parser) -> None:
    if not message.strip():
        raise InvalidMessageError(key, file, "text is empty")
    if message == key or _INTERNAL_CODE_RE.fullmatch(message):
        raise InvalidMessageError(key, file, f"text {message!r} is an internal code, not a label")
    try:
        parser.parse(message)  # pyright: ignore[reportUnknownMemberType]
    except (SyntaxError, ValueError, TypeError) as exc:
        raise InvalidMessageError(key, file, f"not a valid ICU message: {exc}") from None


def _text_and_description(key: str, path: Path, value: object) -> tuple[str, str | None]:
    if isinstance(value, str):
        return value, None
    if isinstance(value, dict):
        message = value.get("text")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        description = value.get("description")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(message, str) and (description is None or isinstance(description, str)):
            return message, description
    raise InvalidMessageError(
        key, path, 'expected "<text>" or {"text": "<text>", "description": "<context>"}'
    )


def _read_file(path: Path, locale: str, parser: Parser) -> list[TermEntry]:
    module_id = path.stem
    if not _MODULE_RE.fullmatch(module_id):
        raise DictionaryError(f"{path.name}: file name must be a module id (snake_case)")
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DictionaryError(f"{path.name}: cannot read JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise DictionaryError(f"{path.name}: expected an object of keys")
    entries: list[TermEntry] = []
    for key, value in raw.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key):
            raise DictionaryError(
                f"{path.name}: {key!r} is not a dotted key such as module.area.name"
            )
        message, description = _text_and_description(key, path, value)
        _check_message(key, path, message, parser)
        entries.append(TermEntry(key, module_id, locale, message, description, path))
    return entries


def read_dictionary(directory: Path) -> list[TermEntry]:
    """Read and validate every ``*.json`` file in ``directory``; raise on the first bad entry."""
    locale = directory.name
    if not _LOCALE_RE.fullmatch(locale):
        raise DictionaryError(f"{directory}: directory name must be a locale such as en-AU")
    files = sorted(directory.glob("*.json"))
    if not files:
        raise DictionaryError(f"{directory}: no *.json dictionary files")
    parser = Parser()
    seen: dict[str, Path] = {}
    entries: list[TermEntry] = []
    for path in files:
        for entry in _read_file(path, locale, parser):
            if entry.key in seen:
                raise DictionaryError(
                    f"{entry.key} is in both {seen[entry.key].name} and {path.name}"
                )
            seen[entry.key] = path
            entries.append(entry)
    return entries


async def load(directory: Path, *, url: str) -> LoadResult:
    """Validate ``directory``, then upsert its keys as platform rows in one transaction.

    ``url`` is the ``aip_owner`` URL (``DATABASE_MIGRATOR_URL``); any other login is refused.
    """
    entries = read_dictionary(directory)  # before any connection: a bad file writes nothing
    inserted = updated = 0
    engine = create_migrator_engine(url)
    try:
        async with with_platform_tenant(engine) as conn:
            for entry in entries:
                row = (
                    await conn.execute(
                        _UPSERT,
                        {
                            "id": UUID(new_request_id()),  # UUIDv7 (ARCH-04)
                            "tenant_id": PLATFORM_TENANT_ID,
                            "key": entry.key,
                            "module_id": entry.module_id,
                            "locale": entry.locale,
                            "text": entry.text,
                            "description": entry.description,
                        },
                    )
                ).one_or_none()
                if row is None:
                    continue
                if row.inserted:
                    inserted += 1
                else:
                    updated += 1
    finally:
        await engine.dispose()
    return LoadResult(inserted, updated, len(entries) - inserted - updated)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m aip.modules.terms.loader <dictionary-dir>", file=sys.stderr)
        return 2
    url = os.environ.get(URL_ENV)
    if not url:
        print(f"{URL_ENV} is not set", file=sys.stderr)
        return 2
    try:
        result = asyncio.run(load(Path(args[0]), url=url))
    except DictionaryError as exc:
        print(f"terms loader: {exc}", file=sys.stderr)
        return 1
    print(
        f"terms loader: {result.inserted} inserted, {result.updated} updated, "
        f"{result.unchanged} unchanged"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
