"""UPLOADS-02 unit tests for the scan reducer: ordering, stop-at-first-fail, and fail-closed."""

from __future__ import annotations

import asyncio
import contextlib
import struct
from collections.abc import AsyncIterator

from aip.modules.uploads.pipeline.clamav_client import ClamdSettings
from aip.modules.uploads.pipeline.reducer import ScanInput, run_scan

MIB = 1024 * 1024
UNREACHABLE = ClamdSettings(host="127.0.0.1", port=1, timeout_s=1.0)


def _png(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)
    )


async def _clamd(reply: bytes) -> AsyncIterator[ClamdSettings]:
    """A stub clamd that answers every command (VERSION and INSTREAM) with ``reply``."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(reader.read(1 << 20), 1.0)
        with contextlib.suppress(Exception):
            writer.write(reply)
            await writer.drain()
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield ClamdSettings(host="127.0.0.1", port=port, timeout_s=2.0)
    finally:
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()


async def test_clean_png_passes_every_stage() -> None:
    scan = ScanInput(_png(800, 600), "image/png", declared_size=MIB, platform_max=100 * MIB)
    async for clamd in _clamd(b"stream: OK\x00"):
        verdict = await run_scan(scan, clamd)
        assert verdict.outcome == "pass"
        assert verdict.detected_mime == "image/png"
        stages = [r.stage for r in verdict.results]
        assert stages == ["size_cap", "magic_bytes", "ratio_cap", "clamav"]


async def test_size_cap_stops_the_pipeline_first() -> None:
    scan = ScanInput(b"x" * 50, "image/png", declared_size=10, platform_max=100 * MIB)
    verdict = await run_scan(scan, UNREACHABLE)  # clamd never reached
    assert verdict.outcome == "fail"
    assert [r.stage for r in verdict.results] == ["size_cap"]


async def test_magic_bytes_mismatch_stops_before_clamav() -> None:
    scan = ScanInput(b"MZ\x90\x00bogus", "image/jpeg", declared_size=MIB, platform_max=100 * MIB)
    verdict = await run_scan(scan, UNREACHABLE)
    assert verdict.outcome == "fail"
    assert [r.stage for r in verdict.results] == ["size_cap", "magic_bytes"]


async def test_oversized_image_fails_at_ratio_cap() -> None:
    scan = ScanInput(_png(20000, 20000), "image/png", declared_size=MIB, platform_max=100 * MIB)
    verdict = await run_scan(scan, UNREACHABLE)
    assert verdict.outcome == "fail"
    assert [r.stage for r in verdict.results] == ["size_cap", "magic_bytes", "ratio_cap"]


async def test_infected_file_fails_at_clamav() -> None:
    scan = ScanInput(_png(10, 10), "image/png", declared_size=MIB, platform_max=100 * MIB)
    async for clamd in _clamd(b"stream: Eicar-Test-Signature FOUND\x00"):
        verdict = await run_scan(scan, clamd)
        assert verdict.outcome == "fail"
        assert verdict.results[-1].stage == "clamav"
        assert verdict.results[-1].detail["signature"] == "Eicar-Test-Signature"


async def test_unreachable_clamd_fails_closed_as_error() -> None:
    scan = ScanInput(_png(10, 10), "image/png", declared_size=MIB, platform_max=100 * MIB)
    verdict = await run_scan(scan, UNREACHABLE)
    assert verdict.outcome == "error"  # never a pass when the scan could not complete
    assert verdict.results[-1].stage == "clamav"
    assert verdict.results[-1].outcome == "error"
