"""UPLOADS-02 unit tests for the clamd client, against local stub sockets (no ClamAV needed)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import pytest

from aip.modules.uploads.pipeline.clamav_client import (
    ClamdError,
    ClamdSettings,
    clamav_stage,
    scan_instream,
    version,
)


async def _serve(reply: bytes | None) -> AsyncIterator[ClamdSettings]:
    """Start a stub clamd on a free port. ``reply`` None means accept but never answer."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(reader.read(1 << 20), 1.0)  # consume the client's command
        if reply is not None:
            writer.write(reply)
            with contextlib.suppress(Exception):
                await writer.drain()
        else:
            await asyncio.sleep(30)  # never answer
        with contextlib.suppress(Exception):
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield ClamdSettings(host="127.0.0.1", port=port, timeout_s=2.0)
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()


async def test_instream_clean_is_not_infected() -> None:
    async for settings in _serve(b"stream: OK\x00"):
        clean, signature = await scan_instream(b"hello world", settings)
        assert clean is True
        assert signature is None


async def test_instream_infected_returns_the_signature() -> None:
    async for settings in _serve(b"stream: Eicar-Test-Signature FOUND\x00"):
        clean, signature = await scan_instream(b"x", settings)
        assert clean is False
        assert signature == "Eicar-Test-Signature"


async def test_clamav_stage_fail_carries_version_and_signature() -> None:
    # VERSION then INSTREAM: the stub answers every command with the same FOUND line, which is
    # enough to exercise the stage's shape (version recorded, infected -> fail).
    async for settings in _serve(b"stream: Win.Test.EICAR FOUND\x00"):
        result = await clamav_stage(b"x", settings)
        assert result.outcome == "fail"
        assert result.detail["signature"] == "Win.Test.EICAR"
        assert "signature_db_version" in result.detail


async def test_unexpected_reply_raises() -> None:
    async for settings in _serve(b"blah\x00"):
        with pytest.raises(ClamdError):
            await scan_instream(b"x", settings)


async def test_silent_server_times_out() -> None:
    async for settings in _serve(None):
        with pytest.raises(ClamdError):
            await version(ClamdSettings(host=settings.host, port=settings.port, timeout_s=0.3))


async def test_connection_refused_raises() -> None:
    # Nothing is listening on port 1; connecting fails fast and surfaces as ClamdError.
    with pytest.raises(ClamdError):
        await scan_instream(b"x", ClamdSettings(host="127.0.0.1", port=1, timeout_s=1.0))
