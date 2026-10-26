"""Stage (d): the ClamAV client — clamd ``INSTREAM`` over TCP (UPLOADS-02 step 3d).

The object is streamed to ``clamd`` in length-prefixed chunks; the ``VERSION`` string is recorded as
``signature_db_version``. A connection, timeout or protocol problem raises ``ClamdError`` so the
pipeline fails closed (the job retries, and the last attempt rejects as ``scan_error``) — a scan
that could not complete never passes.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .types import StageResult

__all__ = ["ClamdError", "ClamdSettings", "clamav_stage", "scan_instream", "version"]

# clamd caps a single INSTREAM chunk at StreamMaxLength; 64 KiB is well under the default and keeps
# the length prefix a plain uint32.
_CHUNK = 64 * 1024


class ClamdError(RuntimeError):
    """clamd was unreachable, timed out, or spoke unexpectedly — the scan did not complete."""


@dataclass(frozen=True)
class ClamdSettings:
    host: str = "clamav"
    port: int = 3310
    timeout_s: float = 60.0


async def _command(
    settings: ClamdSettings, write_body: Callable[[asyncio.StreamWriter], Awaitable[None]]
) -> bytes:
    """Open a connection, run one clamd command, and return its reply line (no trailing NUL)."""
    try:
        async with asyncio.timeout(settings.timeout_s):
            reader, writer = await asyncio.open_connection(settings.host, settings.port)
            try:
                await write_body(writer)
                await writer.drain()
                reply = await reader.readuntil(b"\x00")
            finally:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
    except (TimeoutError, OSError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise ClamdError(f"clamd {settings.host}:{settings.port}: {type(exc).__name__}") from exc
    return reply.rstrip(b"\x00")


async def version(settings: ClamdSettings) -> str:
    """The clamd/engine/signature ``VERSION`` string (recorded as ``signature_db_version``)."""

    async def _write(writer: asyncio.StreamWriter) -> None:
        writer.write(b"zVERSION\x00")

    return (await _command(settings, _write)).decode("utf-8", "replace").strip()


async def scan_instream(data: bytes, settings: ClamdSettings) -> tuple[bool, str | None]:
    """INSTREAM ``data``; return ``(clean, signature)`` (``signature`` set only when infected)."""

    async def _write(writer: asyncio.StreamWriter) -> None:
        writer.write(b"zINSTREAM\x00")
        for start in range(0, len(data), _CHUNK):
            chunk = data[start : start + _CHUNK]
            writer.write(len(chunk).to_bytes(4, "big") + chunk)
        writer.write((0).to_bytes(4, "big"))  # zero-length chunk ends the stream

    reply = (await _command(settings, _write)).decode("utf-8", "replace").strip()
    # "stream: OK" when clean; "stream: <Signature> FOUND" when infected; anything else is an error.
    if reply.endswith("OK"):
        return True, None
    if reply.endswith("FOUND"):
        signature = reply[len("stream: ") : -len(" FOUND")] if ":" in reply else reply
        return False, signature
    raise ClamdError(f"unexpected clamd reply: {reply!r}")


async def clamav_stage(data: bytes, settings: ClamdSettings) -> StageResult:
    """Record the signature version, scan, and return the stage verdict. Raises ``ClamdError`` on a
    scan that could not complete, so the pipeline fails closed."""
    db_version = await version(settings)
    clean, signature = await scan_instream(data, settings)
    if clean:
        return StageResult("clamav", "pass", {"signature_db_version": db_version})
    return StageResult(
        "clamav", "fail", {"signature_db_version": db_version, "signature": signature}
    )
