"""``aip-db snapshot``: a deterministic ``pg_dump --schema-only`` in ``db/schema.snapshot.sql``.

Normalisation strips comment and version header lines, ``SET`` / ``set_config`` lines and psql
``\\restrict`` meta-commands, then sorts objects so the output depends only on the schema. Each
object keeps a ``-- Name: ...; Type: ...; Schema: ...`` line so normalising is idempotent.
Lines inside dollar-quoted function bodies are kept verbatim: a ``-- comment`` or ``SET`` there
is part of the function.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url

_HEADER_RE = re.compile(r"^-- Name: (?P<name>.*?); Type: (?P<type>.*?); Schema: (?P<schema>[^;]*)")
_DROP_PREFIXES = ("--", "SET ", "SELECT pg_catalog.set_config(", "\\restrict", "\\unrestrict")
_DOLLAR_TAG_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")


def pg_dump_command() -> list[str]:
    """``pg_dump``, or the command in ``PG_DUMP`` (CI pins the Postgres 16 client)."""
    return shlex.split(os.environ.get("PG_DUMP", "pg_dump"))


def _dollar_state(line: str, open_tag: str | None) -> str | None:
    """The dollar-quote tag still open after ``line`` (``None`` when outside any body).

    pg_dump writes function bodies as ``$$ ... $$`` or ``$_$ ... $_$``; quotes inside a body
    cannot close it, so only the matching tag is tracked.
    """
    pos = 0
    while True:
        if open_tag is None:
            m = _DOLLAR_TAG_RE.search(line, pos)
            if m is None:
                return None
            open_tag, pos = m.group(0), m.end()
        else:
            end = line.find(open_tag, pos)
            if end == -1:
                return open_tag
            open_tag, pos = None, end + len(open_tag)


def normalise_dump(text: str) -> str:
    blocks: list[tuple[tuple[str, str, str], list[str]]] = []
    key = ("", "", "")
    body: list[str] = []

    def flush() -> None:
        lines = "\n".join(body).strip("\n").splitlines()
        compact: list[str] = []
        for line in lines:
            if line.strip() == "" and (not compact or compact[-1] == ""):
                continue
            compact.append(line.rstrip())
        if compact or key != ("", "", ""):
            blocks.append((key, compact))

    open_tag: str | None = None  # the dollar-quote tag of a function body we are inside
    for raw in text.splitlines():
        if open_tag is not None:
            body.append(raw)  # body lines are kept verbatim, even `-- ...` or `SET ...`
            open_tag = _dollar_state(raw, open_tag)
            continue
        header = _HEADER_RE.match(raw)
        if header:
            flush()
            key = (header["schema"], header["type"], header["name"])
            body = []
        elif not raw.startswith(_DROP_PREFIXES):
            body.append(raw)
            open_tag = _dollar_state(raw, None)
    flush()

    out: list[str] = []
    for (schema, type_, name), lines in sorted(blocks, key=lambda b: (b[0], b[1])):
        chunk = ([f"-- Name: {name}; Type: {type_}; Schema: {schema}"] if name else []) + lines
        while chunk and chunk[-1] == "":
            chunk.pop()
        out.append("\n".join(chunk))
    return "\n\n".join(c for c in out if c) + "\n"


def dump_schema(url: str) -> str:
    """Run ``pg_dump --schema-only`` (password via ``PGPASSWORD``, not the command line)."""
    parsed = make_url(url).set(drivername="postgresql")
    env = dict(os.environ)
    if parsed.password is not None:
        env["PGPASSWORD"] = str(parsed.password)
    dsn = parsed.set(password=None).render_as_string(hide_password=False)
    result = subprocess.run(
        [*pg_dump_command(), "--schema-only", "--no-password", "--dbname", dsn],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")
    return result.stdout


def write_snapshot(url: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(normalise_dump(dump_schema(url)), encoding="utf-8")
    return output
